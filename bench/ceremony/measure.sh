#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
fail=0

if ! command -v ks >/dev/null 2>&1; then
  echo "ceremony measurement requires the installed 'ks' formatter" >&2
  exit 1
fi

printf '%-28s %5s %5s %5s %8s %8s %s\n' TASK KS PY GO KS/PY KS/GO STATUS
for dir in "$root"/[0-9][0-9]-*; do
  task_fail=0
  for file in task.ks task.py task.go; do
    if [[ ! -f "$dir/$file" ]]; then
      echo "missing: $dir/$file" >&2
      fail=1
      task_fail=1
    fi
  done
  [[ $task_fail -eq 0 ]] || continue

  if ! ks --lang en fmt --check "$dir/task.ks" >/dev/null 2>&1; then
    echo "non-canonical Koschei benchmark source: $dir/task.ks" >&2
    echo "run: ks fmt --write $dir/task.ks" >&2
    fail=1
  fi

  canonical_ks="$(ks --lang en fmt "$dir/task.ks")"
  ks_lines=$(printf '%s\n' "$canonical_ks" | awk 'NF && $1 !~ /^\/\//' | wc -l)
  py_lines=$(awk 'NF && $1 !~ /^#/' "$dir/task.py" | wc -l)
  go_lines=$(awk 'NF && $1 !~ /^\/\//' "$dir/task.go" | wc -l)
  py_ratio=$(awk -v ks="$ks_lines" -v ref="$py_lines" 'BEGIN { printf "%.2f", ks/ref }')
  go_ratio=$(awk -v ks="$ks_lines" -v ref="$go_lines" 'BEGIN { printf "%.2f", ks/ref }')
  status=$(awk -v ks="$ks_lines" -v py="$py_lines" -v go="$go_lines" 'BEGIN { print (ks <= py*1.3 && ks <= go) ? "PASS" : "REPORT" }')
  printf '%-28s %5d %5d %5d %8s %8s %s\n' "$(basename "$dir")" "$ks_lines" "$py_lines" "$go_lines" "$py_ratio" "$go_ratio" "$status"
done
exit "$fail"
