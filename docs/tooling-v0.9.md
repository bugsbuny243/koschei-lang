# Koschei v0.9 Tooling Contract

## CLI language

- Default: English.
- Turkish: `ks --lang tr ...` or `KOSCHEI_LANG=tr`.
- Error codes are language-independent and stable within the release line.

## JSON diagnostics

`ks check --json <source-or-project>` writes exactly one JSON object to stdout.
Success uses `ok: true`; failure uses `ok: false` and includes `code`, `title`,
`message`, `source`, `line`, and `column`. Exit status remains authoritative.

## Project manifest

`ks new <name>` creates `koschei.toml`, `src/main.ks`, `.gitignore`, and a README.
The package name and semantic version are validated. The entry path is resolved
against the manifest directory and cannot escape it.

## VS Code

The extension in `editors/vscode` has no runtime npm dependency. It invokes the
installed Koschei CLI and converts the JSON result into a VS Code diagnostic.
