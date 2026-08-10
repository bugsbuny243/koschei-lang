# Koschei Language Foundation Export v1

Status: offline model-training handoff. This is not compiler/runtime integration and grants no authority to a model.

The exporter produces the exact source corpus contract consumed by Koschei Sentinel's language-foundation release gate:

- schema: `koschei.language-foundation-corpus.v1`;
- generator: `koschei-foundation-export/v1`;
- repository: `bugsbuny243/koschei-lang`;
- one exact lowercase 40-character Git commit SHA;
- SHA-256 for every selected source document;
- content-derived document IDs;
- deterministic leakage families;
- one canonical corpus SHA-256.

## Security boundary

The exporter does **not** read selected training documents from the mutable working tree. It enumerates the exact pinned commit with Git and reads each selected blob by object SHA. Therefore untracked files and dirty working-tree edits cannot be mislabeled as content from the pinned commit.

Selected source categories are deliberately narrow:

- root `README.md`, `README.tr.md`, and `README.en.md` when present;
- Markdown references below `docs/`;
- Koschei source files below `examples/`.

Implementation-language source such as Python or Go is not exported as a syntax template. Compiler-oracle generated cases remain a separate training stage governed by `MODEL_TRAINING_CONTRACT.md`.

A selected symlink, non-UTF-8 source, unsafe path, mutable revision name such as `main`/`HEAD`, abbreviated SHA, duplicate output path, or insufficient leakage families causes a hard failure.

## Usage

From a checkout that contains the desired commit object:

```text
ks-foundation-export \
  --repo-root . \
  --source-commit <exact-40-char-commit-sha> \
  --output build/model/language-foundation-corpus.json
```

The output path is no-replace. Re-running into an existing path fails instead of overwriting a previously trusted corpus.

The command reports the corpus SHA-256. That digest and the exact source commit are the two independent values Sentinel must be given when it builds a leakage-safe train/validation/test release.

## Family rule

Family assignment intentionally matches Sentinel v1 exactly:

- all root README language variants share `reference:README`;
- `*.tr.md` / `*.en.md` reference translations share the base Markdown path;
- top-level `examples/*.ks` share `example:top-level`;
- files under `examples/<project>/...` share `example:<project>`.

A family is indivisible during Sentinel splitting, preventing sibling modules and translated reference variants from leaking across train, validation, and test.

## Trust rule

The model learns Koschei from pinned language evidence, but the model never becomes the language authority. Compiler behavior and deterministic capability/security rules remain authoritative as defined by `MODEL_TRAINING_CONTRACT.md`.
