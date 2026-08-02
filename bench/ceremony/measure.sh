#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
fail=0
printf '%-28s %5s %5s %5s %8s %8s %s\n' TASK KS PY GO KS/PY KS/GO STATUS
for dir in "$root"/[0-9][0-9]-*; do
  for file in task.ks task.py task.go; do
    if [[ ! -f "$dir/$file" ]]; then
      echo "missing: $dir/$file" >&2
      fail=1
    fi
  done
  [[ $fail -eq 0 ]] || continue
  ks_lines=$(awk 'NF && $1 !~ /^\/\//' "$dir/task.ks" | wc -l)
  py_lines=$(awk 'NF && $1 !~ /^#/' "$dir/task.py" | wc -l)
  go_lines=$(awk 'NF && $1 !~ /^\/\//' "$dir/task.go" | wc -l)
  py_ratio=$(awk -v ks="$ks_lines" -v ref="$py_lines" 'BEGIN { printf "%.2f", ks/ref }')
  go_ratio=$(awk -v ks="$ks_lines" -v ref="$go_lines" 'BEGIN { printf "%.2f", ks/ref }')
  status=$(awk -v ks="$ks_lines" -v py="$py_lines" -v go="$go_lines" 'BEGIN { print (ks <= py*1.3 && ks <= go) ? "PASS" : "REPORT" }')
  printf '%-28s %5d %5d %5d %8s %8s %s\n' "$(basename "$dir")" "$ks_lines" "$py_lines" "$go_lines" "$py_ratio" "$go_ratio" "$status"
done
exit "$fail"
