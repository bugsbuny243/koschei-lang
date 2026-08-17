"""Koschei (.ks) — capability-secure programming language."""

from __future__ import annotations

__version__ = "0.10.0"

from .cli import main
from .runtime_alignment import install_runtime_alignment

install_runtime_alignment()

from .data_language_v1 import install_data_language_v1

install_data_language_v1()

from .data_mir_v1 import install_data_mir_v1

install_data_mir_v1()

from .data_public_abi_v1 import install_data_public_abi_v1

install_data_public_abi_v1()

from .data_native_source_v1 import install_packaged_native_source

install_packaged_native_source()

from .ergonomics_v010 import install_ergonomics_v010

install_ergonomics_v010()

from .financial_decimal_v1 import install_financial_decimal_v1

install_financial_decimal_v1()

from .financial_decimal_runtime_isolation import install_financial_decimal_runtime_isolation

install_financial_decimal_runtime_isolation()

from .financial_decimal_mir_v1 import install_financial_decimal_mir_v1

install_financial_decimal_mir_v1()

from .financial_decimal_operator_gate import install_financial_decimal_operator_gate

install_financial_decimal_operator_gate()

from .financial_decimal_diagnostics import install_financial_decimal_diagnostics

install_financial_decimal_diagnostics()

from .bounded_queue_v1 import install_bounded_queue_v1

install_bounded_queue_v1()

from .bounded_queue_contract_gate import install_bounded_queue_contract_gate

install_bounded_queue_contract_gate()

from .bounded_queue_mir_v1 import install_bounded_queue_mir_v1

install_bounded_queue_mir_v1()

from .structured_tasks_v1 import install_structured_tasks_v1

install_structured_tasks_v1()

from .structured_tasks_mir_v1 import install_structured_tasks_mir_v1

install_structured_tasks_mir_v1()

from .structured_tasks_runtime_alignment import (
    install_structured_tasks_runtime_alignment,
)

install_structured_tasks_runtime_alignment()

from .structured_task_safety_v1 import install_structured_task_safety_v1

install_structured_task_safety_v1()

from .structured_task_safety_go_alignment import (
    install_structured_task_safety_go_alignment,
)

install_structured_task_safety_go_alignment()

from .structured_task_safety_runtime_names import (
    install_structured_task_safety_runtime_names,
)

install_structured_task_safety_runtime_names()

from .bounded_queue_sync_v1 import install_bounded_queue_sync_v1

install_bounded_queue_sync_v1()

from .deterministic_parallel_map_v1 import install_deterministic_parallel_map_v1

install_deterministic_parallel_map_v1()

from .deterministic_parallel_map_mir_shape_v1 import (
    install_deterministic_parallel_map_mir_shape_v1,
)

install_deterministic_parallel_map_mir_shape_v1()

from .mir_native_module_shadow_guard_v1 import (
    install_mir_native_module_shadow_guard_v1,
)

install_mir_native_module_shadow_guard_v1()

from .fallible_mir_v1 import install_fallible_mir_v1

install_fallible_mir_v1()

from .interpolation_mir_v1 import install_interpolation_mir_v1

install_interpolation_mir_v1()

from .integer_division_mir_v1 import install_integer_division_mir_v1

install_integer_division_mir_v1()

from .direct_mir_type_integrity_v1 import install_direct_mir_type_integrity_v1

install_direct_mir_type_integrity_v1()

from .object_space_error_boundary_v1 import install_object_space_error_boundary_v1

install_object_space_error_boundary_v1()

from .object_space_adversarial_guard_v1 import (
    install_object_space_adversarial_guard_v1,
)

install_object_space_adversarial_guard_v1()

from .object_space_redteam_round2_v1 import install_object_space_redteam_round2_v1

install_object_space_redteam_round2_v1()

from .object_space_redteam_round3_v1 import install_object_space_redteam_round3_v1

install_object_space_redteam_round3_v1()

from .object_space_diagnostic_privacy_v1 import (
    install_object_space_diagnostic_privacy_v1,
)

install_object_space_diagnostic_privacy_v1()

from .object_space_check_v1 import install_object_space_check_v1

install_object_space_check_v1()

from .object_space_check_adversarial_guard_v1 import (
    install_object_space_check_adversarial_guard_v1,
)

install_object_space_check_adversarial_guard_v1()

from .object_space_codegen_alignment_v1 import (
    install_object_space_codegen_alignment_v1,
)

install_object_space_codegen_alignment_v1()

from .object_space_commands_v1 import install_object_space_commands_v1

install_object_space_commands_v1()

from .object_space_frontend_alignment_v1 import (
    install_object_space_frontend_alignment_v1,
)

install_object_space_frontend_alignment_v1()

from .native_relationship_alignment_v1 import install_native_relationship_alignment_v1

install_native_relationship_alignment_v1()

from .native_value_domain_alignment_v1 import install_native_value_domain_alignment_v1

install_native_value_domain_alignment_v1()

from .native_decision_alignment_v1 import install_native_decision_alignment_v1

install_native_decision_alignment_v1()

from .native_reusable_alignment_v1 import install_native_reusable_alignment_v1

install_native_reusable_alignment_v1()

from .native_cell_alignment_v1 import install_native_cell_alignment_v1

install_native_cell_alignment_v1()

from .native_cell_projection_alignment_v1 import (
    install_native_cell_projection_alignment_v1,
)

install_native_cell_projection_alignment_v1()

from .native_cell_reuse_composition_alignment_v1 import (
    install_native_cell_reuse_composition_alignment_v1,
)

install_native_cell_reuse_composition_alignment_v1()

from .native_mixed_reuse_alignment_v1 import install_native_mixed_reuse_alignment_v1

install_native_mixed_reuse_alignment_v1()

from .serve_authority_v1 import install_serve_authority_v1

install_serve_authority_v1()

from .serve_authority_loopback_canonical_v1 import (
    install_serve_authority_loopback_canonical_v1,
)

install_serve_authority_loopback_canonical_v1()

from .serve_authority_diagnostics_v1 import install_serve_authority_diagnostics_v1

install_serve_authority_diagnostics_v1()

from .serve_loopback_exchange_v1 import install_serve_loopback_exchange_v1

install_serve_loopback_exchange_v1()

from .serve_loopback_exchange_member_v1 import (
    install_serve_loopback_exchange_member_v1,
)

install_serve_loopback_exchange_member_v1()

from .serve_loopback_http_strict_v1 import install_serve_loopback_http_strict_v1

install_serve_loopback_http_strict_v1()

from .serve_loopback_exchange_parity_v1 import (
    install_serve_loopback_exchange_parity_v1,
)

install_serve_loopback_exchange_parity_v1()

from .serve_loopback_exchange_go_v1 import install_serve_loopback_exchange_go_v1

install_serve_loopback_exchange_go_v1()

from .serve_loopback_exchange_go_integrity_v1 import (
    install_serve_loopback_exchange_go_integrity_v1,
)

install_serve_loopback_exchange_go_integrity_v1()

from .serve_loopback_exchange_diagnostics_v1 import (
    install_serve_loopback_exchange_diagnostics_v1,
)

install_serve_loopback_exchange_diagnostics_v1()

from .serve_loopback_exchange_catalog_v1 import (
    install_serve_loopback_exchange_catalog_v1,
)

install_serve_loopback_exchange_catalog_v1()

from .persistence_authority_v1 import install_persistence_authority_v1

install_persistence_authority_v1()

from .persistence_policy_canonical_v1 import install_persistence_policy_canonical_v1

install_persistence_policy_canonical_v1()

from .bounded_persistence_v1 import install_bounded_persistence_v1

install_bounded_persistence_v1()

from .persistence_runtime_alignment_v1 import install_persistence_runtime_alignment_v1

install_persistence_runtime_alignment_v1()

from .persistence_parent_integrity_v1 import install_persistence_parent_integrity_v1

install_persistence_parent_integrity_v1()

from .persistence_target_integrity_v1 import install_persistence_target_integrity_v1

install_persistence_target_integrity_v1()

from .persistence_semantic_alignment_v1 import install_persistence_semantic_alignment_v1

install_persistence_semantic_alignment_v1()

from .persistence_diagnostics_v1 import install_persistence_diagnostics_v1

install_persistence_diagnostics_v1()

from .persistence_catalog_v1 import install_persistence_catalog_v1

install_persistence_catalog_v1()

from .persistence_member_v1 import install_persistence_member_v1

install_persistence_member_v1()

from .typestate_affine_alignment import install_typestate_affine_alignment

install_typestate_affine_alignment()

__all__ = ["main"]