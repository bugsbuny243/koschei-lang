import pytest

from koschei.ast_nodes import SourceLocation, StructDeclaration, StructField, TypeRef
from koschei.container_runtime_v1 import ContainerRuntimeError, MapBuilderV1, StructBuilderV1


class _Capability:
    pass


def _contains_capability(value):
    if isinstance(value, _Capability):
        return True
    if isinstance(value, list):
        return any(_contains_capability(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_capability(item) for item in value.values())
    return False


def _runtime_type_name(value):
    if isinstance(value, str):
        return "String"
    if isinstance(value, int) and not isinstance(value, bool):
        return "Int"
    if isinstance(value, _Capability):
        return "Capability"
    return type(value).__name__


def _matches_type(value, expected):
    actual = _runtime_type_name(value)
    return actual in expected


def test_map_rejects_non_string_and_duplicate_keys() -> None:
    location = SourceLocation(1, 1)
    builder = MapBuilderV1.empty()

    with pytest.raises(ContainerRuntimeError, match="Map anahtarı String"):
        builder.insert(
            1,
            "x",
            contains_capability=_contains_capability,
            runtime_type_name=_runtime_type_name,
            location=location,
        )

    builder.insert(
        "name",
        "a",
        contains_capability=_contains_capability,
        runtime_type_name=_runtime_type_name,
        location=location,
    )
    with pytest.raises(ContainerRuntimeError, match="birden fazla"):
        builder.insert(
            "name",
            "b",
            contains_capability=_contains_capability,
            runtime_type_name=_runtime_type_name,
            location=location,
        )


def test_map_rejects_nested_capability_laundering() -> None:
    builder = MapBuilderV1.empty()
    with pytest.raises(ContainerRuntimeError, match="Capability"):
        builder.insert(
            "secret",
            {"nested": _Capability()},
            contains_capability=_contains_capability,
            runtime_type_name=_runtime_type_name,
            location=SourceLocation(2, 1),
        )


def test_struct_rejects_capability_and_wrong_field_type() -> None:
    location = SourceLocation(1, 1)
    declaration = StructDeclaration(
        "Profile",
        (
            StructField("name", TypeRef(("String",), location), location),
            StructField("age", TypeRef(("Int",), location), location),
        ),
        location,
    )
    builder = StructBuilderV1.empty(declaration)

    with pytest.raises(ContainerRuntimeError, match="Capability"):
        builder.set_field(
            "name",
            _Capability(),
            contains_capability=_contains_capability,
            matches_type=_matches_type,
            runtime_type_name=_runtime_type_name,
            location=location,
        )

    with pytest.raises(ContainerRuntimeError, match="age"):
        builder.set_field(
            "age",
            "not-an-int",
            contains_capability=_contains_capability,
            matches_type=_matches_type,
            runtime_type_name=_runtime_type_name,
            location=location,
        )


def test_struct_finish_requires_exact_declared_field_set() -> None:
    location = SourceLocation(1, 1)
    declaration = StructDeclaration(
        "Profile",
        (
            StructField("name", TypeRef(("String",), location), location),
            StructField("age", TypeRef(("Int",), location), location),
        ),
        location,
    )
    builder = StructBuilderV1.empty(declaration)
    builder.set_field(
        "name",
        "Ada",
        contains_capability=_contains_capability,
        matches_type=_matches_type,
        runtime_type_name=_runtime_type_name,
        location=location,
    )

    with pytest.raises(ContainerRuntimeError, match="eksik=age"):
        builder.finish()

    builder.set_field(
        "age",
        37,
        contains_capability=_contains_capability,
        matches_type=_matches_type,
        runtime_type_name=_runtime_type_name,
        location=location,
    )
    value = builder.finish()
    assert value.type_name == "Profile"
    assert value.fields == {"name": "Ada", "age": 37}
