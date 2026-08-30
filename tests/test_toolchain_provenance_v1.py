from dataclasses import replace

import pytest

from koschei.toolchain_provenance_v1 import (
    ToolchainProvenanceV1Error,
    attest_toolchain_provenance_v1,
    measure_toolchain_artifact_v1,
)


def receipt():
    artifact = b"koschei-compiler-artifact-v1"
    key = b"t" * 32
    value = attest_toolchain_provenance_v1(
        toolchain_id="koschei-compiler",
        toolchain_version="0.10.0",
        toolchain_artifact_bytes=artifact,
        build_profile="release-reproducible",
        toolchain_signing_key=key,
    )
    return value, artifact, key


def test_signed_toolchain_binds_exact_artifact_and_identity():
    value, artifact, key = receipt()
    value.assert_authenticated(toolchain_signing_key=key, toolchain_artifact_bytes=artifact)
    assert value.artifact_digest == measure_toolchain_artifact_v1(artifact)
    assert value.authority is False


def test_toolchain_artifact_substitution_rejects():
    value, _, key = receipt()
    with pytest.raises(ToolchainProvenanceV1Error, match="artifact mismatch"):
        value.assert_authenticated(toolchain_signing_key=key, toolchain_artifact_bytes=b"other")


def test_toolchain_version_profile_and_digest_tampering_reject():
    value, artifact, key = receipt()
    for forged in (
        replace(value, toolchain_version="0.10.1"),
        replace(value, build_profile="debug"),
        replace(value, artifact_digest="1" * 64),
    ):
        with pytest.raises(ToolchainProvenanceV1Error):
            forged.assert_authenticated(toolchain_signing_key=key, toolchain_artifact_bytes=artifact)


def test_wrong_toolchain_signing_key_rejects():
    value, artifact, _ = receipt()
    with pytest.raises(ToolchainProvenanceV1Error, match="authentication failed"):
        value.assert_authenticated(toolchain_signing_key=b"x" * 32, toolchain_artifact_bytes=artifact)
