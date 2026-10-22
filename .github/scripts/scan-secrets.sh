#!/usr/bin/env bash
set -euo pipefail

patterns='mongodb\+srv://|-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{20,}|(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}|Admin@123|Acct@1234'

if git grep -n -I -E "$patterns" -- . ':!frontend/package-lock.json' \
    ':!.github/scripts/scan-secrets.sh'; then
  echo "High-confidence credential pattern found in tracked files." >&2
  exit 1
fi

tracked_env="$({ git ls-files | grep -E '(^|/)\.env($|\.)' || true; } | grep -v -E '(^|/)\.env\.example$' || true)"
if [[ -n "$tracked_env" ]]; then
  echo "Environment file must not be tracked:" >&2
  echo "$tracked_env" >&2
  exit 1
fi

echo "Tracked secret scan passed."
