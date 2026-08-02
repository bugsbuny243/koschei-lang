# Koschei ceremony benchmark

This directory contains the first 20 tasks of the planned 30-task benchmark. Every task has equivalent Koschei, Python, and Go source.

`./bench/ceremony/measure.sh` counts non-empty, non-comment source lines and reports `KS/Python` and `KS/Go` ratios. The thresholds remain report-only: `KS <= Python * 1.3` and `KS <= Go`. CI fails only when a triplet is missing, a Koschei program no longer checks, or measurement cannot run. Ratios become a release gate only after the corpus is broad enough and the remaining gaps are addressed with general language features rather than benchmark-specific shortcuts.

Tasks 1-10 cover the original v0.10 core. Tasks 11-20 add collection summaries, stable deduplication, key/value parsing, list transformation, existential search, partitioning, batching, nested flattening, running totals, and record aggregation.

Task 4 intentionally validates and canonicalizes JSON. Data v1 is opaque and does not expose field lookup; changing that ABI is outside the ergonomics release.
