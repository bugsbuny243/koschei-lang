#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
for source in "$root"/bench/ceremony/[0-9][0-9]-*/task.ks; do
  ks --lang en check "$source" >/dev/null
done
"$root/bench/ceremony/measure.sh"
