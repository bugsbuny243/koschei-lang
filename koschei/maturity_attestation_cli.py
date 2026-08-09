"""CLI for deriving protected maturity checks from verified artifacts."""

from __future__ import annotations

import argparse
import json
import sys

from .build_manifest import BuildManifestError, NativeBuildManifest, load_native_manifest, verify_native_manifest
from .lexer import LexerError
from .maturity import load_maturity_evidence
from .maturity_attestation import (
    MaturityAttestationError,
    build_attested_maturity_evidence,
    write_attested_maturity_evidence,
)
from .mir import MirIntegrityError
from .module_lock import ModuleLockError, load_module_lock
from .modules import ModuleError
from .parser import ParserError
from .release_proof import ReleaseProofError, load_release_proof, verify_release_proof
from .reproducibility import (
    ReproducibilityError,
    load_reproducibility_report,
    verify_reproducibility_report,
)
from .semantic import SemanticError

_ERRORS = (
    OSError,
    ValueError,
    BuildManifestError,
    MaturityAttestationError,
    ReleaseProofError,
    ReproducibilityError,
    ModuleLockError,
    ModuleError,
    MirIntegrityError,
    LexerError,
    ParserError,
    SemanticError,
)


def add_maturity_attest_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "maturity-attest",
        help="Derive protected maturity checks from verified release and CI artifacts",
    )
    actions = parser.add_subparsers(dest="maturity_attest_action", required=True)

    create = actions.add_parser("create", help="Create attested maturity evidence")
    _add_inputs(create)
    create.add_argument("--output", required=True)
    create.add_argument("--json", action="store_true")

    verify = actions.add_parser("verify", help="Recompute and verify attested maturity evidence")
    _add_inputs(verify)
    verify.add_argument("--attested-evidence", required=True)
    verify.add_argument("--json", action="store_true")


def command_maturity_attest(args: argparse.Namespace) -> int:
    try:
        base = load_maturity_evidence(args.base_evidence)
        if base.schema_version != "koschei.maturity-evidence.v1":
            raise MaturityAttestationError("KS1940", "base evidence must use schema v1")
        release = _verify_build(args, "release")
        witness = _verify_build(args, "witness")
        report = verify_reproducibility_report(
            load_reproducibility_report(args.report),
            release,
            witness,
        )
        proof = verify_release_proof(
            load_release_proof(args.proof),
            release,
            witness,
            report,
        )
        expected = build_attested_maturity_evidence(
            base,
            proof,
            ci_artifact_path=args.ci_artifact,
            ci_head_sha=args.ci_head_sha,
        )
        if args.maturity_attest_action == "create":
            write_attested_maturity_evidence(expected, args.output)
            path = args.output
            verified = False
        else:
            observed = load_maturity_evidence(args.attested_evidence)
            if observed.schema_version != "koschei.maturity-evidence.v3":
                raise MaturityAttestationError("KS1944", "evidence is not attested v3")
            if observed.canonical_payload != expected:
                raise MaturityAttestationError(
                    "KS1944",
                    "attested maturity evidence does not match supplied verified artifacts",
                )
            path = args.attested_evidence
            verified = True
    except _ERRORS as error:
        return _render_error(args, error)

    result = {
        "ok": True,
        "verified": verified,
        "path": path,
        "release_proof_digest": expected["release_proof_digest"],
        "release_artifact_sha256": expected["release_artifact_sha256"],
        "ci_artifact_sha256": expected["ci_artifact_sha256"],
        "ci_head_sha": expected["ci_head_sha"],
        "ci_test_count": expected["ci_test_count"],
        "ci_warning_count": expected["ci_warning_count"],
        "derived_checks": expected["derived_checks"],
        "attestation_digest": expected["attestation_digest"],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        label = "VERIFIED" if verified else "CREATED"
        print(f"KOSCHEI MATURITY ATTESTATION: {label}")
        print(f"RELEASE PROOF: {expected['release_proof_digest']}")
        print(f"CI ARTIFACT: {expected['ci_artifact_sha256']}")
        print(f"ATTESTATION: {expected['attestation_digest']}")
    return 0


def _verify_build(args: argparse.Namespace, prefix: str) -> NativeBuildManifest:
    return verify_native_manifest(
        load_native_manifest(getattr(args, f"{prefix}_manifest")),
        getattr(args, f"{prefix}_artifact"),
        source=getattr(args, f"{prefix}_source"),
        locked=load_module_lock(getattr(args, f"{prefix}_lockfile")),
    )


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-evidence", required=True)
    for prefix in ("release", "witness"):
        parser.add_argument(f"--{prefix}-source", required=True)
        parser.add_argument(f"--{prefix}-artifact", required=True)
        parser.add_argument(f"--{prefix}-manifest", required=True)
        parser.add_argument(f"--{prefix}-lockfile", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--proof", required=True)
    parser.add_argument("--ci-artifact", required=True)
    parser.add_argument("--ci-head-sha", required=True)


def _render_error(args: argparse.Namespace, error: Exception) -> int:
    code = getattr(error, "code", "KS1940")
    if getattr(args, "json", False):
        print(
            json.dumps(
                {"ok": False, "code": code, "message": str(error)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    else:
        print(f"KOSCHEI ERROR: {error}", file=sys.stderr)
    return 1
