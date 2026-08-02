"""Install the isolated Koschei v0.10 ergonomics surface."""
from .ergonomics_nodes import install_node_references
from .ergonomics_syntax import install_syntax_v010
from .ergonomics_semantics import install_semantics_v010
from .ergonomics_runtime import install_runtime_v010
from .ergonomics_integration import install_integration_v010
from .ergonomics_diagnostics import install_diagnostics_v010
from .ergonomics_collections_v0101 import install_collections_v0101
from .ergonomics_search_v0102 import install_search_v0102
from .ergonomics_daily_collections_v0103 import install_daily_collections_v0103
from .ergonomics_nested_generics_v0104 import install_nested_generics_v0104
from .ergonomics_numeric_reductions_v0105 import install_numeric_reductions_v0105
from .ergonomics_stable_unique_v0106 import install_stable_unique_v0106

_INSTALLED = False


def install_ergonomics_v010() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    install_node_references()
    install_syntax_v010()
    install_semantics_v010()
    install_runtime_v010()
    install_integration_v010()
    install_diagnostics_v010()
    install_collections_v0101()
    install_search_v0102()
    install_daily_collections_v0103()
    install_nested_generics_v0104()
    install_numeric_reductions_v0105()
    install_stable_unique_v0106()
    _INSTALLED = True
