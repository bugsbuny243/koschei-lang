#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
for source in "$root"/bench/ceremony/[0-9][0-9]-*/task.ks; do
  task="$(basename "$(dirname "$source")")"
  printf 'CHECK %-28s' "$task"
  if ks --lang en check "$source" >/dev/null; then
    echo ' PASS'
  else
    echo ' FAIL' >&2
    exit 1
  fi
done
"$root/bench/ceremony/measure.sh"
