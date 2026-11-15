#!/bin/sh
# Encrypted off-site copy of the newest verified Design Saga backup.
#
# Does nothing (exit 0) until a target is configured, so it is safe to install
# early. Configure in /etc/design-saga/offsite.env (root-only, read by the
# systemd unit); see docs/runbooks/OFFSITE-BACKUP-AND-ALERTS.md.
#
# Targets (first one set wins):
#   DESIGN_SAGA_OFFSITE_SSH_TARGET=user@host:/path   SSH/SFTP storage (storage box, second VPS, NAS)
#   DESIGN_SAGA_OFFSITE_RCLONE_TARGET=remote:bucket/path   any rclone remote (needs rclone installed)
#   DESIGN_SAGA_OFFSITE_DIR=/mnt/offsite             a mounted off-host filesystem
#
# Every run: verify the local backup checksums, tar + gpg AES-256 encrypt with
# the passphrase file, decrypt once to prove the archive is readable, upload
# the archive and its .sha256, delete remote archives older than
# DESIGN_SAGA_OFFSITE_KEEP_DAYS, and record success/failure for the monitor.
set -eu
umask 077

backup_root=${DESIGN_SAGA_BACKUP_ROOT:-/opt/design-saga-backups}
state_dir=${DESIGN_SAGA_OFFSITE_STATE_DIR:-/var/lib/design-saga-offsite}
passphrase_file=${DESIGN_SAGA_OFFSITE_PASSPHRASE_FILE:-/etc/design-saga/offsite.passphrase}
ssh_target=${DESIGN_SAGA_OFFSITE_SSH_TARGET:-}
ssh_key=${DESIGN_SAGA_OFFSITE_SSH_KEY:-/etc/design-saga/offsite_ed25519}
ssh_port=${DESIGN_SAGA_OFFSITE_SSH_PORT:-22}
rclone_target=${DESIGN_SAGA_OFFSITE_RCLONE_TARGET:-}
dir_target=${DESIGN_SAGA_OFFSITE_DIR:-}
keep_days=${DESIGN_SAGA_OFFSITE_KEEP_DAYS:-30}

case "$keep_days" in ''|*[!0-9]*) echo "DESIGN_SAGA_OFFSITE_KEEP_DAYS must be a whole number" >&2; exit 2 ;; esac

if [ -z "$ssh_target" ] && [ -z "$rclone_target" ] && [ -z "$dir_target" ]; then
  echo "Off-site backup is not configured; nothing to do."
  exit 0
fi

mkdir -p "$state_dir"
archive=""
fail() {
  date -u +%Y-%m-%dT%H:%M:%SZ > "$state_dir/last-failure"
  printf '%s\n' "$1" > "$state_dir/last-failure-reason"
  logger -p user.err -t design-saga-offsite "Off-site backup failed: $1" 2>/dev/null || true
  echo "Off-site backup failed: $1" >&2
  [ -z "$archive" ] || rm -f "$archive" "$archive.sha256"
  exit 1
}
trap 'fail "unexpected error (exit $?)"' HUP INT TERM

[ -s "$passphrase_file" ] || fail "passphrase file $passphrase_file is missing or empty"

latest=$(find "$backup_root" -mindepth 1 -maxdepth 1 -type d -name '20??????T??????Z' \
  -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
[ -n "$latest" ] || fail "no backup directory in $backup_root"
name=$(basename "$latest")
(cd "$latest" && sha256sum -c SHA256SUMS >/dev/null 2>&1) || fail "local backup $name failed its checksums"

archive="$state_dir/design-saga-$name.tar.gpg"
tar -C "$backup_root" -cf - "$name" | \
  gpg --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$passphrase_file" \
      --symmetric --cipher-algo AES256 -o "$archive" || fail "encryption of $name failed"
gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$passphrase_file" -d "$archive" 2>/dev/null | \
  tar -tf - >/dev/null || fail "the encrypted archive of $name could not be read back"
(cd "$state_dir" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256") || \
  fail "could not checksum the encrypted archive"
base=$(basename "$archive")
cutoff=$(date -u -d "-$keep_days days" +%Y%m%dT%H%M%SZ 2>/dev/null || echo "")

old_names() {   # stdin: file names; prints archives older than the cutoff
  [ -n "$cutoff" ] || return 0
  sed -n 's/^.*\(design-saga-\(20[0-9]\{6\}T[0-9]\{6\}Z\)\.tar\.gpg\)$/\2 \1/p' | \
    while read -r stamp file; do
      [ "$stamp" \< "$cutoff" ] && printf '%s\n' "$file"
    done
  return 0
}

if [ -n "$ssh_target" ]; then
  host=${ssh_target%%:*}
  rpath=${ssh_target#*:}
  [ "$host" != "$ssh_target" ] && [ -n "$rpath" ] || fail "DESIGN_SAGA_OFFSITE_SSH_TARGET must look like user@host:/path"
  [ -r "$ssh_key" ] || fail "SSH key $ssh_key is not readable"
  opts="-i $ssh_key -P $ssh_port -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=30"
  # sftp batch works on SFTP-only storage boxes as well as normal SSH servers.
  printf 'put %s %s/%s.part\nput %s %s/%s.sha256\nrename %s/%s.part %s/%s\n' \
    "$archive" "$rpath" "$base" "$archive.sha256" "$rpath" "$base" "$rpath" "$base" "$rpath" "$base" | \
    sftp $opts -b - "$host" >/dev/null || fail "upload to $host failed"
  listing=$(printf 'ls -1 %s\n' "$rpath" | sftp $opts -b - "$host" 2>/dev/null) || fail "listing $host failed"
  printf '%s\n' "$listing" | grep -q "$base" || fail "uploaded archive is not listed on $host"
  for old in $(printf '%s\n' "$listing" | old_names); do
    printf 'rm %s/%s\nrm %s/%s.sha256\n' "$rpath" "$old" "$rpath" "$old" | sftp $opts -b - "$host" >/dev/null 2>&1 || true
  done
elif [ -n "$rclone_target" ]; then
  command -v rclone >/dev/null 2>&1 || fail "rclone is not installed"
  rclone copy "$archive" "$rclone_target" && rclone copy "$archive.sha256" "$rclone_target" || \
    fail "rclone upload to $rclone_target failed"
  rclone check --one-way "$state_dir" "$rclone_target" --include "$base" >/dev/null 2>&1 || \
    fail "rclone could not confirm $base on $rclone_target"
  for old in $(rclone lsf "$rclone_target" 2>/dev/null | old_names); do
    rclone deletefile "$rclone_target/$old" >/dev/null 2>&1 || true
    rclone deletefile "$rclone_target/$old.sha256" >/dev/null 2>&1 || true
  done
else
  [ -d "$dir_target" ] || fail "DESIGN_SAGA_OFFSITE_DIR $dir_target is not a directory"
  cp "$archive" "$dir_target/$base.part" && mv "$dir_target/$base.part" "$dir_target/$base" && \
    cp "$archive.sha256" "$dir_target/" || fail "copy to $dir_target failed"
  (cd "$dir_target" && sha256sum -c "$base.sha256" >/dev/null 2>&1) || fail "copy in $dir_target failed its checksum"
  for old in $(ls -1 "$dir_target" | old_names); do
    rm -f "$dir_target/$old" "$dir_target/$old.sha256"
  done
fi

sha=$(cut -d' ' -f1 "$archive.sha256")
rm -f "$archive" "$archive.sha256"
date -u +%Y-%m-%dT%H:%M:%SZ > "$state_dir/last-success"
printf '{"backup":"%s","archive":"%s","sha256":"%s"}\n' "$name" "$base" "$sha" > "$state_dir/last-success.json"
logger -t design-saga-offsite "Off-site backup stored: $base sha256=$sha" 2>/dev/null || true
echo "Off-site backup stored: $base"
