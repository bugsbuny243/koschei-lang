"""Canonical first-run profile for Qwen/Qwen3.5-397B-A17B inside Koschei.

The official checkpoint is a Qwen3.5 MoE model with a 60-layer hybrid text
backbone. The first Koschei specialization deliberately uses its causal-LM text
path only and keeps the initial adapter surface conservative. The profile also
seals the optimizer/training recipe so the same Koschei plan cannot silently run
with different learning dynamics.

Reference posture for v1:
- causal-LM text path only; vision frozen;
- MoE router and expert weights frozen;
- LoRA on full-attention and Gated-DeltaNet projections only;
- router logits enabled for auxiliary load-balancing evidence;
- cache disabled with gradient checkpointing;
- one epoch over the 1,344-example canonical train split on eight devices;
- batch 1/device, no gradient accumulation (global batch 8);
- AdamW fused, 2e-5 cosine LR, 0.01 weight decay, 3% warmup;
- DeepSpeed ZeRO-3; assistant-target-only loss; no packing.

This is a training configuration commitment, not execution authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .native_intelligence_v1 import CANONICAL_BASE_MODEL_V1

_CTX = b"koschei.native-intelligence-qwen397b-profile/v1\x00"

OFFICIAL_ARCHITECTURE = "qwen3_5_moe"
OFFICIAL_TEXT_MODEL_CLASS = "Qwen3_5MoeForCausalLM"
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
    model_class: str
    text_hidden_size: int
    text_layers: int
    experts: int
    experts_per_token: int
    native_context: int
    dtype: str
    vision_depth: int
    full_attention_interval: int
    specialization_mode: str
    text_only_causal_lm: bool
    freeze_vision: bool
    freeze_router: bool
    freeze_experts: bool
    output_router_logits: bool
    use_cache: bool
    lora_rank: int
    lora_alpha: int
    lora_dropout_per_mille: int
    max_sequence_length: int
    gradient_checkpointing: bool
    target_modules: tuple[str, ...]
    num_train_epochs: int
    per_device_train_batch_size: int
    per_device_eval_batch_size: int
    gradient_accumulation_steps: int
    learning_rate_millionths: int
    weight_decay_per_mille: int
    warmup_per_mille: int
    lr_scheduler: str
    optimizer: str
    max_grad_norm_milli: int
    deepspeed_stage: int
    eval_steps: int
    save_steps: int
    save_total_limit: int
    logging_steps: int
    seed: int
    assistant_target_only_loss: bool
    packing: bool
    bf16: bool
    tf32: bool
    authority: bool
    digest: str
    version: int = 1

    def assert_sealed(self) -> None:
        if self.version != 1:
            raise Qwen397BProfileError("unsupported Qwen397B Koschei profile version")
        expected_facts = {
            "base_model_id": CANONICAL_BASE_MODEL_V1,
            "architecture": OFFICIAL_ARCHITECTURE,
            "model_class": OFFICIAL_TEXT_MODEL_CLASS,
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
        if self.text_only_causal_lm is not True:
            raise Qwen397BProfileError("first Koschei run must use the causal-LM text path")
        if not (self.freeze_vision and self.freeze_router and self.freeze_experts):
            raise Qwen397BProfileError(
                "first Koschei run must freeze vision, router and expert weights"
            )
        if self.output_router_logits is not True:
            raise Qwen397BProfileError(
                "first Koschei run must preserve router auxiliary-loss evidence"
            )
        if self.use_cache is not False:
            raise Qwen397BProfileError("first Koschei training run must disable inference cache")
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

        recipe = {
            "num_train_epochs": 1,
            "per_device_train_batch_size": 1,
            "per_device_eval_batch_size": 1,
            "gradient_accumulation_steps": 1,
            "learning_rate_millionths": 20,
            "weight_decay_per_mille": 10,
            "warmup_per_mille": 30,
            "lr_scheduler": "cosine",
            "optimizer": "adamw_torch_fused",
            "max_grad_norm_milli": 1000,
            "deepspeed_stage": 3,
            "eval_steps": 21,
            "save_steps": 21,
            "save_total_limit": 3,
            "logging_steps": 5,
            "seed": 42,
            "assistant_target_only_loss": True,
            "packing": False,
            "bf16": True,
            "tf32": True,
        }
        for field, expected in recipe.items():
            if getattr(self, field) != expected:
                raise Qwen397BProfileError(f"first Koschei training recipe drift: {field}")
        if self.authority is not False:
            raise Qwen397BProfileError("training profile cannot carry authority")
        expected = _hash(self._payload())
        if self.digest != expected:
            raise Qwen397BProfileError("Qwen397B Koschei profile seal mismatch")

    def _payload(self) -> dict[str, object]:
        return {
            "base_model_id": self.base_model_id,
            "architecture": self.architecture,
            "model_class": self.model_class,
            "text_hidden_size": self.text_hidden_size,
            "text_layers": self.text_layers,
            "experts": self.experts,
            "experts_per_token": self.experts_per_token,
            "native_context": self.native_context,
            "dtype": self.dtype,
            "vision_depth": self.vision_depth,
            "full_attention_interval": self.full_attention_interval,
            "specialization_mode": self.specialization_mode,
            "text_only_causal_lm": self.text_only_causal_lm,
            "freeze_vision": self.freeze_vision,
            "freeze_router": self.freeze_router,
            "freeze_experts": self.freeze_experts,
            "output_router_logits": self.output_router_logits,
            "use_cache": self.use_cache,
            "lora_rank": self.lora_rank,
            "lora_alpha": self.lora_alpha,
            "lora_dropout_per_mille": self.lora_dropout_per_mille,
            "max_sequence_length": self.max_sequence_length,
            "gradient_checkpointing": self.gradient_checkpointing,
            "target_modules": list(self.target_modules),
            "num_train_epochs": self.num_train_epochs,
            "per_device_train_batch_size": self.per_device_train_batch_size,
            "per_device_eval_batch_size": self.per_device_eval_batch_size,
            "gradient_accumulation_steps": self.gradient_accumulation_steps,
            "learning_rate_millionths": self.learning_rate_millionths,
            "weight_decay_per_mille": self.weight_decay_per_mille,
            "warmup_per_mille": self.warmup_per_mille,
            "lr_scheduler": self.lr_scheduler,
            "optimizer": self.optimizer,
            "max_grad_norm_milli": self.max_grad_norm_milli,
            "deepspeed_stage": self.deepspeed_stage,
            "eval_steps": self.eval_steps,
            "save_steps": self.save_steps,
            "save_total_limit": self.save_total_limit,
            "logging_steps": self.logging_steps,
            "seed": self.seed,
            "assistant_target_only_loss": self.assistant_target_only_loss,
            "packing": self.packing,
            "bf16": self.bf16,
            "tf32": self.tf32,
            "authority": False,
        }


def canonical_qwen397b_koschei_profile_v1() -> Qwen397BKoscheiTrainingProfileV1:
    result = Qwen397BKoscheiTrainingProfileV1(
        base_model_id=CANONICAL_BASE_MODEL_V1,
        architecture=OFFICIAL_ARCHITECTURE,
        model_class=OFFICIAL_TEXT_MODEL_CLASS,
        text_hidden_size=OFFICIAL_TEXT_HIDDEN_SIZE,
        text_layers=OFFICIAL_TEXT_LAYERS,
        experts=OFFICIAL_EXPERTS,
        experts_per_token=OFFICIAL_EXPERTS_PER_TOKEN,
        native_context=OFFICIAL_MAX_POSITION_EMBEDDINGS,
        dtype=OFFICIAL_DTYPE,
        vision_depth=OFFICIAL_VISION_DEPTH,
        full_attention_interval=OFFICIAL_FULL_ATTENTION_INTERVAL,
        specialization_mode="text-koschei-lora-v1",
        text_only_causal_lm=True,
        freeze_vision=True,
        freeze_router=True,
        freeze_experts=True,
        output_router_logits=True,
        use_cache=False,
        lora_rank=16,
        lora_alpha=32,
        lora_dropout_per_mille=50,
        max_sequence_length=4096,
        gradient_checkpointing=True,
        target_modules=CANONICAL_LORA_TARGETS_V1,
        num_train_epochs=1,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate_millionths=20,
        weight_decay_per_mille=10,
        warmup_per_mille=30,
        lr_scheduler="cosine",
        optimizer="adamw_torch_fused",
        max_grad_norm_milli=1000,
        deepspeed_stage=3,
        eval_steps=21,
        save_steps=21,
        save_total_limit=3,
        logging_steps=5,
        seed=42,
        assistant_target_only_loss=True,
        packing=False,
        bf16=True,
        tf32=True,
        authority=False,
        digest="",
    )
    object.__setattr__(result, "digest", _hash(result._payload()))
    result.assert_sealed()
    return result
