# Koschei ceremony benchmark

This directory is the first 10-task core of the planned 30-task benchmark. Every task has equivalent Koschei, Python, and Go source.

`./bench/ceremony/measure.sh` counts non-empty, non-comment source lines and reports `KS/Python` and `KS/Go` ratios. In v0.10 the thresholds are report-only: `KS <= Python * 1.3` and `KS <= Go`. CI fails only when a triplet is missing, a Koschei program no longer checks, or measurement cannot run. The ratio becomes a release gate after two measurement releases.

Task 4 intentionally validates and canonicalizes JSON. Data v1 is opaque and does not expose field lookup; changing that ABI is outside the ergonomics release.
