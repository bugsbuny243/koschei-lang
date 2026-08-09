"""CLI for creating and verifying Koschei reproducible release proofs."""

from __future__ import annotations

import argparse
import json
import sys

from .build_manifest import (
    BuildManifestError,
    NativeBuildManifest,
    load_native_manifest,
    verify_native_manifest,
)
from .lexer import LexerError
from .mir import MirIntegrityError
from .module_lock import ModuleLockError, load_module_lock
from .modules import ModuleError
from .parser import ParserError
from .release_proof import (
    ReleaseProofError,
    build_release_proof,
    load_release_proof,
    verify_release_proof,
    write_release_proof,
)
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
    ReleaseProofError,
    ReproducibilityError,
    ModuleLockError,
    ModuleError,
    MirIntegrityError,
    LexerError,
    ParserError,
    SemanticError,
)


def add_release_proof_parser(subcommands: argparse._SubParsersAction) -> None:
    parser = subcommands.add_parser(
        "release-proof",
        help="Create or verify a sealed byte-reproducible native release proof",
    )
    _add_language(parser)
    actions = parser.add_subparsers(dest="release_proof_action", required=True)

    create = actions.add_parser("create", help="Create a reproducible release proof")
    _add_language(create)
    _add_inputs(create)
    create.add_argument("--output", required=True, help="Release proof output path")
    create.add_argument("--json", action="store_true", help="Emit stable JSON")

    verify = actions.add_parser("verify", help="Verify an existing release proof")
    _add_language(verify)
    _add_inputs(verify)
    verify.add_argument("--proof", required=True, help="Existing release proof path")
    verify.add_argument("--json", action="store_true", help="Emit stable JSON")


def command_release_proof(args: argparse.Namespace) -> int:
    try:
        release = _verify_build(args, "release")
        witness = _verify_build(args, "witness")
        report = verify_reproducibility_report(
            load_reproducibility_report(args.report),
            release,
            witness,
        )
        if args.release_proof_action == "create":
            proof = build_release_proof(release, witness, report)
            write_release_proof(proof, args.output)
            output_path = args.output
            verified = False
        else:
            proof = verify_release_proof(
                load_release_proof(args.proof),
                release,
                witness,
                report,
            )
            output_path = args.proof
            verified = True
    except _ERRORS as error:
        return _render_error(args, error)

    result = {
        "ok": True,
        "verified": verified,
        "state": proof.state,
        "authority": proof.authority,
        "release_artifact_sha256": proof.release_artifact_sha256,
        "witness_artifact_sha256": proof.witness_artifact_sha256,
        "reproducibility_report_digest": proof.reproducibility_report_digest,
        "proof_digest": proof.proof_digest,
        "owner_approval_required": proof.owner_approval_required,
        "automatic_publish_allowed": proof.automatic_publish_allowed,
        "production_integration_allowed": proof.production_integration_allowed,
        "path": output_path,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0

    locale = getattr(args, "lang", "en")
    if verified:
        label = "DOĞRULANDI" if locale == "tr" else "VERIFIED"
    else:
        label = "OLUŞTURULDU" if locale == "tr" else "CREATED"
    print(f"KOSCHEI RELEASE PROOF: {label}")
    print(f"ARTIFACT SHA256: {proof.release_artifact_sha256}")
    print(f"PROOF DIGEST: {proof.proof_digest}")
    return 0


def _verify_build(args: argparse.Namespace, prefix: str) -> NativeBuildManifest:
    return verify_native_manifest(
        load_native_manifest(getattr(args, f"{prefix}_manifest")),
        getattr(args, f"{prefix}_artifact"),
        source=getattr(args, f"{prefix}_source"),
        locked=load_module_lock(getattr(args, f"{prefix}_lockfile")),
    )


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    for prefix in ("release", "witness"):
        parser.add_argument(f"--{prefix}-source", required=True)
        parser.add_argument(f"--{prefix}-artifact", required=True)
        parser.add_argument(f"--{prefix}-manifest", required=True)
        parser.add_argument(f"--{prefix}-lockfile", required=True)
    parser.add_argument("--report", required=True, help="Verified reproducibility report")


def _add_language(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lang",
        choices=("en", "tr"),
        default=argparse.SUPPRESS,
        help="Diagnostic language: en or tr",
    )


def _render_error(args: argparse.Namespace, error: Exception) -> int:
    code = getattr(error, "code", "KS1930")
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
