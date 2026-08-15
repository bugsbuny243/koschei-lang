# Koschei ceremony benchmark

This directory contains the first 20 tasks of the planned 30-task benchmark. Every task has equivalent Koschei, Python, and Go source.

`./bench/ceremony/measure.sh` reports non-empty, non-comment source lines and the `KS/Python` and `KS/Go` ratios. Koschei is never measured from author-controlled physical line breaks: every `task.ks` must pass `ks fmt --check`, and the line count is taken from the canonical `ks fmt` output. Packing declarations, loops, functions, or other blocks onto one physical line therefore cannot improve a score and instead fails CI.

The thresholds remain report-only: `KS <= Python * 1.3` and `KS <= Go`. CI fails when a triplet is missing, a Koschei program no longer checks, a Koschei benchmark is not canonically formatted, or measurement cannot run. Ratios become a release gate only after the corpus is broad enough and the remaining gaps are addressed with general language features rather than benchmark-specific shortcuts or formatting tricks.

Tasks 1-10 cover the original v0.10 core. Tasks 11-20 add collection summaries, stable deduplication, key/value parsing, list transformation, existential search, partitioning, batching, nested flattening, running totals, and record aggregation.

Task 4 intentionally validates and canonicalizes JSON. Data v1 is opaque and does not expose field lookup; changing that ABI is outside the ergonomics release.
