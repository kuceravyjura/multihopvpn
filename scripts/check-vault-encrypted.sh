#!/usr/bin/env bash
# Fails if any vault file in the repo is not encrypted. Used by CI and the pre-commit hook.
set -euo pipefail

status=0
while IFS= read -r -d '' f; do
  if ! head -n1 "$f" | grep -q '^\$ANSIBLE_VAULT'; then
    echo "NOT ENCRYPTED: $f"
    status=1
  fi
done < <(find . -path ./ansible/collections -prune -o -name 'vault.yml' -print0)

[ "$status" -eq 0 ] && echo "All vault files are encrypted."
exit "$status"
