#!/usr/bin/env bash
set -euo pipefail

# Keep upstream code and other digests if main advanced during generation.
for attempt in 1 2 3; do
  git fetch origin main
  git rebase origin/main
  if git push origin HEAD:main; then
    exit 0
  fi
  sleep "$((attempt * 2))"
done
echo "Publishing failed after three attempts." >&2
exit 1
