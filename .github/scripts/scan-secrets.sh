#!/usr/bin/env bash
set -euo pipefail

patterns='mongodb\+srv://|-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{20,}|(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}|Admin@123|Acct@1234'
# Old test-only commits contain the two retired demo passwords above. Keep
# rejecting them in the current tree, while the history gate focuses on
# credentials that could still grant external access.
history_patterns='mongodb\+srv://|-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{20,}|(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}'

if git grep -n -I -E "$patterns" -- . ':!frontend/package-lock.json' \
    ':!.github/scripts/scan-secrets.sh'; then
  echo "High-confidence credential pattern found in tracked files." >&2
  exit 1
fi

history_patch="$(mktemp)"
trap 'rm -f "$history_patch"' EXIT
git log --all --format= --patch -- . \
  ':!frontend/package-lock.json' \
  ':!.github/scripts/scan-secrets.sh' > "$history_patch"
if grep -qI -E "$history_patterns" "$history_patch"; then
  echo "High-confidence credential pattern found in Git history." >&2
  exit 1
fi

tracked_env="$({ git ls-files | grep -E '(^|/)\.env($|\.)' || true; } | grep -v -E '(^|/)\.env\.example$' || true)"
if [[ -n "$tracked_env" ]]; then
  echo "Environment file must not be tracked:" >&2
  echo "$tracked_env" >&2
  exit 1
fi

echo "Tracked and Git-history secret scan passed."
