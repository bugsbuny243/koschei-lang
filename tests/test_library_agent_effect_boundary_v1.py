from dataclasses import replace

import pytest

from koschei.library_agent_effect_boundary_v1 import (
    AgentEffectBoundaryError,
    bind_agent_effect_to_koschei,
    effect_classes,
    seal_agent_effect_intent,
)
from koschei.native_sigil_mir_v1 import lower_native_sigils
from koschei.parser import parse


def _mir():
    return lower_native_sigils(parse("ka workspace; vor deploy_gate; shi evidence; thal recovery; nur view;"))


def _intent(**overrides):
    values = dict(
        agent_identity_digest="agent-identity",
        task_digest="task-123",
        artifact_digest="artifact-abc",
        tool="shell",
        effect_class="deploy",
        target="production/api",
        operation="release",
        epoch=7,
        nonce_digest="nonce-1",
    )
    values.update(overrides)
    return seal_agent_effect_intent(**values)


def test_agent_effect_binds_to_vor_subject_and_exact_intent():
    mir = _mir()
    intent = _intent()
    bound = bind_agent_effect_to_koschei(
        mir,
        intent,
        vor_subject="deploy_gate",
        effect_id="effect-1",
    )
    bound.assert_sealed(mir)
    assert bound.canonical_request.subject == "deploy_gate"
    assert bound.canonical_request.request_digest == intent.digest
    assert bound.canonical_request.identity_digest == "agent-identity"
    assert bound.canonical_request.epoch == 7
    assert bound.canonical_request.operation.startswith("agent.deploy:")


def test_agent_cannot_invent_authority_subject_outside_vor():
    with pytest.raises(Exception):
        bind_agent_effect_to_koschei(
            _mir(),
            _intent(),
            vor_subject="workspace",
            effect_id="effect-1",
        )


def test_artifact_or_task_change_produces_different_request_identity():
    mir = _mir()
    first = bind_agent_effect_to_koschei(
        mir, _intent(), vor_subject="deploy_gate", effect_id="effect-1"
    )
    second = bind_agent_effect_to_koschei(
        mir,
        _intent(artifact_digest="artifact-def"),
        vor_subject="deploy_gate",
        effect_id="effect-1",
    )
    third = bind_agent_effect_to_koschei(
        mir,
        _intent(task_digest="task-999"),
        vor_subject="deploy_gate",
        effect_id="effect-1",
    )
    assert first.canonical_request.digest != second.canonical_request.digest
    assert first.canonical_request.digest != third.canonical_request.digest


def test_epoch_or_nonce_change_invalidates_request_reuse():
    mir = _mir()
    first = bind_agent_effect_to_koschei(
        mir, _intent(), vor_subject="deploy_gate", effect_id="effect-1"
    )
    later_epoch = bind_agent_effect_to_koschei(
        mir, _intent(epoch=8), vor_subject="deploy_gate", effect_id="effect-1"
    )
    new_nonce = bind_agent_effect_to_koschei(
        mir,
        _intent(nonce_digest="nonce-2"),
        vor_subject="deploy_gate",
        effect_id="effect-1",
    )
    assert first.canonical_request.digest != later_epoch.canonical_request.digest
    assert first.canonical_request.digest != new_nonce.canonical_request.digest


def test_tampered_agent_intent_fails_closed():
    intent = _intent()
    tampered = replace(intent, target="production/admin")
    with pytest.raises(AgentEffectBoundaryError):
        tampered.assert_sealed()


def test_effect_taxonomy_is_library_surface_not_language_vocabulary():
    assert {"read", "write", "execute", "secret", "merge", "deploy", "sign", "admin"}.issubset(
        set(effect_classes())
    )
