#!/usr/bin/env bash
#
# verify.sh — Koschei release gate.
#
# Answers three questions before a release:
#   1. Does every example still produce the output it produced last time?
#   2. Does every code block in the docs actually compile?
#   3. Does the malicious supply-chain package still fail to compile?
#
# No dependencies. Run from the repository root:
#
#   ./verify.sh                  full check, exits non-zero on failure
#   ./verify.sh --update-golden  record current example output as expected
#   ./verify.sh --soft-docs      report doc failures but do not fail the build
#
set -uo pipefail

cd "$(dirname "$0")"

KS="python3 -m koschei"
GOLDEN_DIR="tests/golden"
UPDATE_GOLDEN=0
SOFT_DOCS=0
FAILED=0
WARNED=0

for arg in "$@"; do
  case "$arg" in
    --update-golden) UPDATE_GOLDEN=1 ;;
    --soft-docs)     SOFT_DOCS=1 ;;
    -h|--help)       sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 64 ;;
  esac
done

if [ -t 1 ]; then
  G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; N=$'\033[0m'
else
  G=""; R=""; Y=""; D=""; N=""
fi

pass() { printf "  ${G}PASS${N}  %s\n" "$1"; }
fail() { printf "  ${R}FAIL${N}  %s\n" "$1"; FAILED=$((FAILED + 1)); }
warn() { printf "  ${Y}WARN${N}  %s\n" "$1"; WARNED=$((WARNED + 1)); }
skip() { printf "  ${D}skip${N}  %s\n" "$1"; }
head_() { printf "\n${D}==>${N} %s\n" "$1"; }

# ---------------------------------------------------------------- preflight

command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }
$KS version >/dev/null 2>&1 || { echo "cannot run 'python3 -m koschei' from $(pwd)"; exit 1; }

printf "Koschei verify — %s\n" "$($KS version 2>/dev/null)"

# ------------------------------------------------------------- 1. test suite

head_ "Test suite"
if out=$(python3 -m unittest discover -s tests 2>&1); then
  pass "$(printf '%s' "$out" | grep -oE 'Ran [0-9]+ tests' | head -1) — $(printf '%s' "$out" | tail -1)"
else
  fail "unit tests failed"
  printf '%s\n' "$out" | tail -15 | sed 's/^/        /'
fi

# ------------------------------------------------ 2. examples vs golden output
#
# Each entry: <path>|<mode>
#   run   — must run successfully; stdout is compared against the golden file
#   check — must pass `ks check` (library module with no main)
#   deny  — must FAIL, and the failure must mention the given code

EXAMPLES=(
  "examples/app.ks|run"
  "examples/capability.ks|run"
  "examples/control_flow.ks|run"
  "examples/daily.ks|run"
  "examples/hello.ks|run"
  "examples/holders.ks|run"
  "examples/maps.ks|run"
  "examples/runtime_demo.ks|run"
  "examples/showcase.ks|run"
  "examples/v08_types.ks|run"
  "examples/risk.ks|check"
  "examples/supply_chain/main.ks|deny:KS2401"
)

head_ "Examples"
mkdir -p "$GOLDEN_DIR"

for entry in "${EXAMPLES[@]}"; do
  path="${entry%%|*}"
  mode="${entry##*|}"

  if [ ! -f "$path" ]; then
    fail "$path — file is missing"
    continue
  fi

  case "$mode" in
    run)
      golden="$GOLDEN_DIR/$(printf '%s' "$path" | tr '/' '_').txt"
      actual=$($KS run "$path" 2>&1)
      status=$?
      if [ $status -ne 0 ]; then
        fail "$path — expected to run, exited $status"
        printf '%s\n' "$actual" | head -3 | sed 's/^/        /'
        continue
      fi
      if [ $UPDATE_GOLDEN -eq 1 ]; then
        printf '%s\n' "$actual" > "$golden"
        pass "$path — golden recorded"
      elif [ ! -f "$golden" ]; then
        warn "$path — no golden file yet (run with --update-golden)"
      elif [ "$actual" = "$(cat "$golden")" ]; then
        pass "$path"
      else
        fail "$path — output changed"
        diff <(cat "$golden") <(printf '%s\n' "$actual") | head -10 | sed 's/^/        /'
      fi
      ;;
    check)
      if $KS check "$path" >/dev/null 2>&1; then
        pass "$path (check only)"
      else
        fail "$path — check failed"
      fi
      ;;
    deny:*)
      want="${mode#deny:}"
      actual=$($KS check "$path" 2>&1)
      if printf '%s' "$actual" | grep -q "$want"; then
        pass "$path — correctly rejected with $want"
      else
        fail "$path — SECURITY: expected rejection with $want"
        printf '%s\n' "$actual" | head -3 | sed 's/^/        /'
      fi
      ;;
  esac
done

# ------------------------------------------------------ 3. documentation code
#
# Every ```ks block that contains a top-level declaration (fn / struct / enum /
# import) must compile. Blocks without one are treated as illustrative
# fragments and skipped. To skip a full block deliberately, put this line
# immediately before it in the markdown:
#
#   <!-- verify: skip -->

head_ "Documentation code blocks"

DOC_TMP=$(mktemp -d)
trap 'rm -rf "$DOC_TMP"' EXIT

python3 - "$DOC_TMP" <<'PY'
import pathlib, sys

out = pathlib.Path(sys.argv[1])
roots = ["README.md", "README.tr.md"]
for directory in ("docs", "design"):
    root = pathlib.Path(directory)
    if root.is_dir():
        roots.extend(sorted(str(p) for p in root.glob("*.md")))

index = []
for name in roots:
    path = pathlib.Path(name)
    if not path.is_file():
        continue
    lines = path.read_text(encoding="utf-8").splitlines()
    inside = False
    skip_next = False
    expect_next = ""
    buffer, start = [], 0
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        low = stripped.lower()
        if not inside and low.startswith("<!-- verify: skip"):
            skip_next = True
            continue
        if not inside and low.startswith("<!-- verify: future"):
            expect_next = "FUTURE"
            continue
        if not inside and low.startswith("<!-- verify: expect"):
            parts = stripped.replace("-->", "").split()
            expect_next = parts[-1] if parts else ""
            continue
        if not inside and stripped.startswith("```ks"):
            inside, buffer, start = True, [], number
            continue
        if inside and stripped.startswith("```"):
            inside = False
            body = "\n".join(buffer)
            if skip_next:
                index.append(f"{name}\t{start}\tSKIPMARK\t")
                skip_next = expect_next = ""
                skip_next = False
                continue
            if expect_next:
                target = out / f"{name.replace('/', '_')}__{start}.ks"
                target.write_text(body + "\n", encoding="utf-8")
                index.append(f"{name}\t{start}\tEXPECT:{expect_next}\t{target}")
                expect_next = ""
                continue
            skip_next = False
            has_decl = any(
                b.startswith(("fn ", "struct ", "enum ", "import "))
                for b in (l.rstrip() for l in buffer)
            )
            if not has_decl:
                index.append(f"{name}\t{start}\tFRAGMENT\t")
                continue
            target = out / f"{name.replace('/', '_')}__{start}.ks"
            target.write_text(body + "\n", encoding="utf-8")
            runnable = any(
                l.rstrip().startswith("fn main(") for l in buffer
            )
            index.append(
                f"{name}\t{start}\t{'RUN' if runnable else 'COMPILE'}\t{target}"
            )
            continue
        if inside:
            buffer.append(line)
        elif stripped and not stripped.startswith("```"):
            skip_next = False

(out / "index.tsv").write_text("\n".join(index) + "\n", encoding="utf-8")
PY

doc_failures=0
while IFS=$'\t' read -r doc line kind target; do
  [ -z "${doc:-}" ] && continue
  case "$kind" in
    FRAGMENT)  skip "$doc:$line — fragment" ;;
    SKIPMARK)  skip "$doc:$line — marked verify: skip" ;;
    EXPECT:FUTURE)
      landed=0
      if $KS check "$target" >/dev/null 2>&1; then
        if grep -q '^fn main(' "$target"; then
          $KS run "$target" >/dev/null 2>&1 && landed=1
        else
          landed=1
        fi
      fi
      if [ $landed -eq 1 ]; then
        printf "  ${G}NEW!${N}  %s — this v5 feature now compiles. Update the guide.\n" "$doc:$line"
        WARNED=$((WARNED + 1))
      else
        skip "$doc:$line — v5 design, not implemented yet"
      fi
      ;;
    EXPECT:*)
      want="${kind#EXPECT:}"
      out=$($KS check "$target" 2>&1)
      if printf '%s' "$out" | grep -q "$want"; then
        pass "$doc:$line — correctly rejected with $want"
      else
        fail "$doc:$line — expected rejection with $want, did not get it"
        doc_failures=$((doc_failures + 1))
      fi
      ;;
    RUN)
      if out=$($KS check "$target" 2>&1); then
        if out=$($KS run "$target" 2>&1); then
          pass "$doc:$line (compiles and runs)"
        else
          code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
          if [ $SOFT_DOCS -eq 1 ]; then
            warn "$doc:$line — check passes but RUN fails ${code:+($code)}"
          else
            fail "$doc:$line — check passes but RUN fails ${code:+($code)}"
          fi
          doc_failures=$((doc_failures + 1))
          printf '%s\n' "$out" | head -2 | sed 's/^/        /'
        fi
      else
        code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
        if [ $SOFT_DOCS -eq 1 ]; then
          warn "$doc:$line — does not compile ${code:+($code)}"
        else
          fail "$doc:$line — does not compile ${code:+($code)}"
        fi
        doc_failures=$((doc_failures + 1))
        printf '%s\n' "$out" | head -2 | sed 's/^/        /'
      fi
      ;;
    COMPILE)
      if out=$($KS check "$target" 2>&1); then
        pass "$doc:$line ${D}(check only — add 'fn main' to verify at runtime)${N}"
      else
        code=$(printf '%s' "$out" | grep -oE 'KS[0-9]{4}' | head -1)
        if [ $SOFT_DOCS -eq 1 ]; then
          warn "$doc:$line — does not compile ${code:+($code)}"
        else
          fail "$doc:$line — does not compile ${code:+($code)}"
        fi
        doc_failures=$((doc_failures + 1))
        printf '%s\n' "$out" | head -2 | sed 's/^/        /'
      fi
      ;;
  esac
done < "$DOC_TMP/index.tsv"

if [ $doc_failures -gt 0 ]; then
  printf "\n  ${D}A documented example that does not compile is a promise the\n"
  printf "  project is not keeping. Fix the code, fix the doc, or mark the\n"
  printf "  block with <!-- verify: skip --> and say why.${N}\n"
fi

# ------------------------------------------------------------------- summary

head_ "Summary"
if [ $FAILED -eq 0 ] && [ $WARNED -eq 0 ]; then
  printf "  ${G}Everything the repository claims is true.${N}\n\n"
  exit 0
elif [ $FAILED -eq 0 ]; then
  printf "  ${Y}%d warning(s), no failures.${N}\n\n" "$WARNED"
  exit 0
else
  printf "  ${R}%d failure(s)${N}, %d warning(s).\n\n" "$FAILED" "$WARNED"
  exit 1
fi
