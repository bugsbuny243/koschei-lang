# Koschei All-or-Nothing v1 (Nidavellir)

Status: **in-memory rule verified in every executor; atomic `disk.write`**

Nidavellir is the forge of the library universe (see
`KOSCHEI_KUTUPHANE_EVRENLERI_V1.md`): Stormbreaker is forged only when the
star's full heat passes through. Its rule: **a value or a write is built
completely or not at all.** Nothing half-built is ever observable, and code
that runs after a failure never reads half-built data.

This is the lesson of PHP2Shell CVE-2026-109618, where a structure was marked
as holding an entry before the entry's memory existed, and request cleanup
read the stale bytes after memory ran out.

## In memory

A struct literal whose field fails is the Error itself:

```ks
struct Pair {
    label: String,
    count: Int,
}

fn main() {
    let max = 9223372036854775807
    let direct = Pair { label: "c", count: max + 1 }
    let recovered = direct or Pair { label: "rescued", count: 0 }
    println(recovered)
}
```

`direct` is the `KS3501` Error, never a `Pair` with a missing or poisoned
field. Sealed MIR builds a struct in a builder that is not a value until
`MirStructFinish` has every declared field; a failing field value replaces the
whole result. The checked-AST interpreter, the canonical MIR executor, the
direct MIR runtime and MIR-Go binaries agree
(`tests/test_nidavellir_all_or_nothing_v1.py`).

Koschei has no destructors or `finally` blocks, so no user code runs on a
half-built value during a budget stop (`KS3601`, `KS3502`, `KS3105`): the
program stops instead.

## On disk

`disk.write` replaces a file atomically:

1. the text goes to a fresh file beside the target (`.ks-write-<random>.tmp`,
   created exclusively, mode `0600`);
2. the bytes reach the disk with `fsync`;
3. one `rename` puts the new file in the target's place;
4. the directory is synced so the rename survives a crash.

A write that fails or is cut short (no space, a killed process, a crash)
leaves the previous file untouched and removes the temporary file. A reader
sees the old content or the new content, never a mix.

Before this rule `disk.write` truncated the target and then wrote into it: a
failure lost the old content and left a partial file that later reads
accepted as valid.

The rename replaces the directory entry, so:

- a symlink at the target is still refused (`KS3402`);
- a directory at the target is still an error;
- existing permissions are kept; new files are `0600`;
- a hard link to another file is **never written through**. The old
  truncate-and-write path wrote into the shared inode, so a hard link placed
  inside the disk scope could redirect a write to a file outside it. Linux
  `fs.protected_hardlinks` limits who can create such links; the rename makes
  the write safe either way.

## Not covered yet

- Multi-file writes: two `disk.write` calls are two separate atomic steps,
  not one transaction.
- The legacy AST-Go backend still truncates and writes; it is never used to
  produce production binaries (`KS4004`).
- Persistence stores follow their own rules (`docs/BOUNDED_PERSISTENCE_NATIVE_GO_V1.md`).
