"""Generic AI-agent effect boundary for Koschei Library v1.

This adapter does not make Koschei specific to any one agent, IDE, chat product,
or model provider.  It converts an agent-originated tool/effect request into the
same canonical privileged-effect request already enforced by native Koschei MIR,
Universe, Library proof, request binding and replay protection.

The rule is simple: an agent may propose code or a tool action, but proposal is
not authority.  Privileged authority remains explicit and must be represented by
a `vor` subject in the sealed Koschei program.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .native_sigil_mir_v1 import NativeSigilMir
from .native_sigil_request_binding_v1 import CanonicalEffectRequest, seal_effect_request

_CTX = b"koschei.library-agent-effect-boundary/v1\x00"


class AgentEffectBoundaryError(ValueError):
    pass


# These are effect classes, not new Koschei language words.  They describe the
# external operation an agent wants to perform at an adapter boundary.
_EFFECT_CLASSES = frozenset(
    {
        "read",
        "write",
        "execute",
        "network",
        "secret",
        "merge",
        "deploy",
        "sign",
        "admin",
    }
)


@dataclass(frozen=True, slots=True)
class AgentEffectIntent:
    agent_identity_digest: str
    task_digest: str
    artifact_digest: str
    tool: str
    effect_class: str
    target: str
    operation: str
    epoch: int
    nonce_digest: str
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.effect_class not in _EFFECT_CLASSES:
            raise AgentEffectBoundaryError(
                f"unknown agent effect class: {self.effect_class!r}"
            )
        if self.epoch < 0:
            raise AgentEffectBoundaryError("agent effect epoch cannot be negative")
        expected = _intent_digest(
            self.agent_identity_digest,
            self.task_digest,
            self.artifact_digest,
            self.tool,
            self.effect_class,
            self.target,
            self.operation,
            self.epoch,
            self.nonce_digest,
        )
        if self.digest != expected:
            raise AgentEffectBoundaryError("agent effect intent seal mismatch")


@dataclass(frozen=True, slots=True)
class AgentBoundaryRequest:
    intent: AgentEffectIntent
    canonical_request: CanonicalEffectRequest
    subject: str
    digest: str
    version: int = 1

    def assert_sealed(self, mir: NativeSigilMir) -> None:
        self.intent.assert_sealed()
        self.canonical_request.assert_sealed(mir)
        if self.canonical_request.subject != self.subject:
            raise AgentEffectBoundaryError("agent boundary subject mismatch")
        if self.canonical_request.request_digest != self.intent.digest:
            raise AgentEffectBoundaryError("canonical request is not bound to agent intent")
        expected = _boundary_digest(
            self.intent.digest,
            self.canonical_request.digest,
            self.subject,
        )
        if self.digest != expected:
            raise AgentEffectBoundaryError("agent boundary request seal mismatch")


def _require_text(*values: str) -> None:
    if any(not value for value in values):
        raise AgentEffectBoundaryError("agent effect fields cannot be empty")


def _intent_digest(
    agent_identity_digest: str,
    task_digest: str,
    artifact_digest: str,
    tool: str,
    effect_class: str,
    target: str,
    operation: str,
    epoch: int,
    nonce_digest: str,
) -> str:
    _require_text(
        agent_identity_digest,
        task_digest,
        artifact_digest,
        tool,
        effect_class,
        target,
        operation,
        nonce_digest,
    )
    payload = "\n".join(
        (
            f"agent={agent_identity_digest}",
            f"task={task_digest}",
            f"artifact={artifact_digest}",
            f"tool={tool}",
            f"class={effect_class}",
            f"target={target}",
            f"operation={operation}",
            f"epoch={epoch}",
            f"nonce={nonce_digest}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"intent\x00" + payload).hexdigest()


def _boundary_digest(intent_digest: str, request_digest: str, subject: str) -> str:
    payload = "\n".join(
        (
            f"intent={intent_digest}",
            f"request={request_digest}",
            f"subject={subject}",
        )
    ).encode("utf-8")
    return hashlib.sha256(_CTX + b"boundary\x00" + payload).hexdigest()


def seal_agent_effect_intent(
    *,
    agent_identity_digest: str,
    task_digest: str,
    artifact_digest: str,
    tool: str,
    effect_class: str,
    target: str,
    operation: str,
    epoch: int,
    nonce_digest: str,
) -> AgentEffectIntent:
    if effect_class not in _EFFECT_CLASSES:
        raise AgentEffectBoundaryError(f"unknown agent effect class: {effect_class!r}")
    if epoch < 0:
        raise AgentEffectBoundaryError("agent effect epoch cannot be negative")
    digest = _intent_digest(
        agent_identity_digest,
        task_digest,
        artifact_digest,
        tool,
        effect_class,
        target,
        operation,
        epoch,
        nonce_digest,
    )
    result = AgentEffectIntent(
        agent_identity_digest=agent_identity_digest,
        task_digest=task_digest,
        artifact_digest=artifact_digest,
        tool=tool,
        effect_class=effect_class,
        target=target,
        operation=operation,
        epoch=epoch,
        nonce_digest=nonce_digest,
        digest=digest,
    )
    result.assert_sealed()
    return result


def bind_agent_effect_to_koschei(
    mir: NativeSigilMir,
    intent: AgentEffectIntent,
    *,
    vor_subject: str,
    effect_id: str,
) -> AgentBoundaryRequest:
    """Bind one agent action to a Koschei `vor` authority subject.

    `vor_subject` is validated by `seal_effect_request`; an agent cannot invent a
    new privileged subject outside the compiler-produced Koschei policy/program.
    The canonical request payload digest is the sealed agent intent itself, so
    changing agent identity, task, artifact, tool, target, epoch or nonce creates
    a different request and invalidates any previously bound proof.
    """

    mir.assert_sealed()
    intent.assert_sealed()
    operation = f"agent.{intent.effect_class}:{intent.tool}:{intent.operation}:{intent.target}"
    request = seal_effect_request(
        mir,
        effect_id=effect_id,
        subject=vor_subject,
        operation=operation,
        request_digest=intent.digest,
        identity_digest=intent.agent_identity_digest,
        epoch=intent.epoch,
        nonce_digest=intent.nonce_digest,
    )
    result = AgentBoundaryRequest(
        intent=intent,
        canonical_request=request,
        subject=vor_subject,
        digest=_boundary_digest(intent.digest, request.digest, vor_subject),
    )
    result.assert_sealed(mir)
    return result


def effect_classes() -> tuple[str, ...]:
    return tuple(sorted(_EFFECT_CLASSES))
