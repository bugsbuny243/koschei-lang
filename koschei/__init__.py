"""Koschei (.ks) — capability-secure programming language."""

from __future__ import annotations

__version__ = "0.10.0"

from .cli import main
from .runtime_alignment import install_runtime_alignment

install_runtime_alignment()

from .data_language_v1 import install_data_language_v1

install_data_language_v1()

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

from .typestate_affine_alignment import install_typestate_affine_alignment

install_typestate_affine_alignment()

__all__ = ["main"]