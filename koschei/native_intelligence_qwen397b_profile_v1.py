"""Canonical first-run profile for Qwen/Qwen3.5-397B-A17B inside Koschei.

This profile records the official architecture facts that matter to the first
Koschei specialization run and deliberately chooses a conservative adapter
surface:

- text backbone only;
- vision tower frozen;
- MoE router and expert weights frozen;
- LoRA on full-attention and Gated-DeltaNet projection paths only.

The goal of v1 is to teach Koschei language/Universe reasoning without letting a
small initial corpus rewrite routing physics across 512 experts. This is a
training configuration commitment, not execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .native_intelligence_v1 import CANONICAL_BASE_MODEL_V1

_CTX = b"koschei.native-intelligence-qwen397b-profile/v1\x00"

OFFICIAL_ARCHITECTURE = "qwen3_5_moe"
OFFICIAL_TEXT_HIDDEN_SIZE = 4096
OFFICIAL_TEXT_LAYERS = 60
OFFICIAL_EXPERTS = 512
OFFICIAL_EXPERTS_PER_TOKEN = 10
OFFICIAL_MAX_POSITION_EMBEDDINGS = 262_144
OFFICIAL_DTYPE = "bfloat16"
OFFICIAL_VISION_DEPTH = 27
OFFICIAL_FULL_ATTENTION_INTERVAL = 4

FULL_ATTENTION_TARGETS = (
    "self_attn.q_proj",
    "self_attn.k_proj",
    "self_attn.v_proj",
    "self_attn.o_proj",
)
LINEAR_ATTENTION_TARGETS = (
    "linear_attn.in_proj_qkv",
    "linear_attn.in_proj_z",
    "linear_attn.in_proj_b",
    "linear_attn.in_proj_a",
    "linear_attn.out_proj",
)
CANONICAL_LORA_TARGETS_V1 = FULL_ATTENTION_TARGETS + LINEAR_ATTENTION_TARGETS


class Qwen397BProfileError(ValueError):
    pass


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _hash(payload: object) -> str:
    return hashlib.sha256(_CTX + _canonical_json(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class Qwen397BKoscheiTrainingProfileV1:
    base_model_id: str
    architecture: str
    text_hidden_size: int
    text_layers: int
    experts: int
    experts_per_token: int
    native_context: int
    dtype: str
    vision_depth: int
    full_attention_interval: int
    specialization_mode: str
    freeze_vision: bool
    freeze_router: bool
    freeze_experts: bool
    lora_rank: int
    lora_alpha: int
    lora_dropout_per_mille: int
    max_sequence_length: int
    gradient_checkpointing: bool
    target_modules: tuple[str, ...]
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise Qwen397BProfileError("unsupported Qwen397B Koschei profile version")
        expected_facts = {
            "base_model_id": CANONICAL_BASE_MODEL_V1,
            "architecture": OFFICIAL_ARCHITECTURE,
            "text_hidden_size": OFFICIAL_TEXT_HIDDEN_SIZE,
            "text_layers": OFFICIAL_TEXT_LAYERS,
            "experts": OFFICIAL_EXPERTS,
            "experts_per_token": OFFICIAL_EXPERTS_PER_TOKEN,
            "native_context": OFFICIAL_MAX_POSITION_EMBEDDINGS,
            "dtype": OFFICIAL_DTYPE,
            "vision_depth": OFFICIAL_VISION_DEPTH,
            "full_attention_interval": OFFICIAL_FULL_ATTENTION_INTERVAL,
        }
        for field, expected in expected_facts.items():
            if getattr(self, field) != expected:
                raise Qwen397BProfileError(f"Qwen397B architecture drift: {field}")
        if self.specialization_mode != "text-koschei-lora-v1":
            raise Qwen397BProfileError("non-canonical Koschei specialization mode")
        if not (self.freeze_vision and self.freeze_router and self.freeze_experts):
            raise Qwen397BProfileError(
                "first Koschei run must freeze vision, router and expert weights"
            )
        if self.lora_rank != 16 or self.lora_alpha != 32:
            raise Qwen397BProfileError("first Koschei LoRA rank/alpha drift")
        if self.lora_dropout_per_mille != 50:
            raise Qwen397BProfileError("first Koschei LoRA dropout drift")
        if self.max_sequence_length != 4096:
            raise Qwen397BProfileError("first Koschei sequence length drift")
        if self.gradient_checkpointing is not True:
            raise Qwen397BProfileError("first Koschei run requires gradient checkpointing")
        if self.target_modules != CANONICAL_LORA_TARGETS_V1:
            raise Qwen397BProfileError("first Koschei LoRA target surface drift")
        if self.authority is not False:
            raise Qwen397BProfileError("training profile cannot carry authority")
        expected = _hash(self._payload())
        if self.digest != expected:
            raise Qwen397BProfileError("Qwen397B Koschei profile seal mismatch")

    def _payload(self) -> dict[str, object]:
        return {
            "base_model_id": self.base_model_id,
            "architecture": self.architecture,
            "text_hidden_size": self.text_hidden_size,
            "text_layers": self.text_layers,
            "experts": self.experts,
            "experts_per_token": self.experts_per_token,
            "native_context": self.native_context,
            "dtype": self.dtype,
            "vision_depth": self.vision_depth,
            "full_attention_interval": self.full_attention_interval,
            "specialization_mode": self.specialization_mode,
            "freeze_vision": self.freeze_vision,
            "freeze_router": self.freeze_router,
            "freeze_experts": self.freeze_experts,
            "lora_rank": self.lora_rank,
            "lora_alpha": self.lora_alpha,
            "lora_dropout_per_mille": self.lora_dropout_per_mille,
            "max_sequence_length": self.max_sequence_length,
            "gradient_checkpointing": self.gradient_checkpointing,
            "target_modules": list(self.target_modules),
            "authority": False,
        }


def canonical_qwen397b_koschei_profile_v1() -> Qwen397BKoscheiTrainingProfileV1:
    result = Qwen397BKoscheiTrainingProfileV1(
        base_model_id=CANONICAL_BASE_MODEL_V1,
        architecture=OFFICIAL_ARCHITECTURE,
        text_hidden_size=OFFICIAL_TEXT_HIDDEN_SIZE,
        text_layers=OFFICIAL_TEXT_LAYERS,
        experts=OFFICIAL_EXPERTS,
        experts_per_token=OFFICIAL_EXPERTS_PER_TOKEN,
        native_context=OFFICIAL_MAX_POSITION_EMBEDDINGS,
        dtype=OFFICIAL_DTYPE,
        vision_depth=OFFICIAL_VISION_DEPTH,
        full_attention_interval=OFFICIAL_FULL_ATTENTION_INTERVAL,
        specialization_mode="text-koschei-lora-v1",
        freeze_vision=True,
        freeze_router=True,
        freeze_experts=True,
        lora_rank=16,
        lora_alpha=32,
        lora_dropout_per_mille=50,
        max_sequence_length=4096,
        gradient_checkpointing=True,
        target_modules=CANONICAL_LORA_TARGETS_V1,
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(result._payload()))
    result.assert_sealed()
    return result
