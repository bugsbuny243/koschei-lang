# Sample Koschei Security Pilot Report

This sample uses the repository's deliberately malicious supply-chain example. It demonstrates the form of evidence a paid pilot delivers; it is not a claim about a real customer system.

## Executive result

**Finding:** the imported analytics component attempts to read `/etc/app/secrets.env` without receiving disk authority.

**Koschei result:** compile-time rejection with `KS2401`. The unauthorized file read is not executed.

**Recommended policy:** the analytics component should remain pure with respect to disk, environment, process, and network access unless a narrowly scoped capability is intentionally delegated.

## Intended behavior

The component is intended to accept an event and perform analytics logic. Reading application secrets is not part of the stated requirement.

## Negative attack case

Representative malicious behavior:

```ks
fn track(event: String) -> String or Error {
    let secret = disk.read("/etc/app/secrets.env") or return Error("unreadable")
    return secret
}
```

The component has no disk capability value in scope.

## Compiler evidence

Expected security diagnostic:

```text
KS2401: Required capability is unavailable in this scope
```

Security meaning: the attempted side effect requires authority that the function does not possess.

The program fails before runtime execution of the unauthorized read.

## Minimum-authority conclusion

For the stated analytics behavior, this sample requires **no disk authority**. Therefore the minimum-authority design is not to grant a disk capability at all.

A remediation that simply hands the component a broad root disk token would defeat the purpose of the analysis. The correct fix is to remove the unauthorized behavior or, only when the business requirement genuinely needs file access, delegate the narrowest explicit capability that satisfies that requirement.

## CI recommendation

For a component that should stay pure, enforce a policy equivalent to:

```sh
ks check <program>
ks caps --deny disk <program>
ks caps --deny net <program>
ks caps --deny env <program>
ks caps --deny process <program>
```

A future dependency update that requests a forbidden authority domain should fail CI instead of being accepted silently.

## What this proves

For the checked Koschei program and compiler revision, the unauthorized operation is rejected by the compiler's capability rules and does not reach normal execution.

## What this does not prove

This evidence does not prove that the host operating system, compiler binary, developer machine, credentials, build infrastructure, or all application code are uncompromisable. It also does not turn an arbitrary non-Koschei dependency into a protected component without a migration or isolation boundary.

## Follow-on migration decision

A real customer pilot concludes with one of three recommendations:

1. **Keep pure** — the component does not need side-effect authority; enforce denial in CI.
2. **Narrow authority** — delegate a restricted disk/network/environment/process capability matching the actual requirement.
3. **Do not migrate yet** — the component depends on host behavior that the current Koschei runtime/toolchain cannot represent safely enough; document the gap instead of faking coverage.
