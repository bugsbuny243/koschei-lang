import importlib.util
import inspect
from pathlib import Path
import tempfile

import pytest

from koschei.canonical_materialization_handle_v1 import (
    CanonicalMaterializationEffectGateV1,
    CanonicalMaterializationHandleV1Error,
    CanonicalMaterializationRegistryV1,
)
from koschei.continuity_epoch_authority_v1 import (
    ContinuityEpochAuthorityV1Error,
    bind_continuity_epoch_authority_v1,
)
from koschei.nur_nyr_observation_gate_v1 import NyrObservationGateV1
from koschei.nur_nyr_projection_v2 import NyrProjectionV2ReplayError
from koschei.representation_reconstruction_gate_v1 import (
    ReconstructionConsumptionLedgerV1,
    RepresentationReconstructionGateV1,
    RepresentationReconstructionGateV1Error,
)


def _load_materialization_fixture():
    path = Path(__file__).with_name("test_canonical_materialization_handle_v1.py")
    spec = importlib.util.spec_from_file_location(
        "koschei_test_materialization_fixture_v1",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _observer(world, fixture, continuity):
    return NyrObservationGateV1(
        mir=world["mir"],
        veyra=world["veyra"],
        envelope=world["reconstruct_gate"].envelope,
        veil_key=fixture.VEIL,
        continuity=continuity,
    )


def _fresh_reconstruction_gate(world, fixture, continuity):
    registry = CanonicalMaterializationRegistryV1(
        materialization_key=fixture.MATERIALIZE
    )
    gate = RepresentationReconstructionGateV1(
        representation=world["representation"],
        hidden_mir=world["mir"],
        veyra=world["veyra"],
        envelope=world["reconstruct_gate"].envelope,
        grant=world["grant"],
        request=world["request"],
        veil_key=fixture.VEIL,
        reconstruction_key=fixture.RECON,
        receipt_key=fixture.RECEIPT,
        continuity=continuity,
        ledger=ReconstructionConsumptionLedgerV1(),
        materialization_registry=registry,
    )
    return gate


def test_one_continuity_epoch_drives_observation_reconstruction_and_constitutional_materialization():
    fixture = _load_materialization_fixture()
    with tempfile.TemporaryDirectory() as directory:
        world = fixture.build_world(directory)
        try:
            observer = _observer(world, fixture, world["continuity"])
            assert observer.render(world["representation"].surface) == world["representation"].surface.render()

            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")
            stale_reconstruction = _fresh_reconstruction_gate(
                world,
                fixture,
                world["continuity"],
            )
            effect_gate = fixture.effect_gate(world, handle)

            world["backing"]["epoch"] = 8

            with pytest.raises(NyrProjectionV2ReplayError, match="expired"):
                observer.render(world["representation"].surface)

            with pytest.raises(
                RepresentationReconstructionGateV1Error,
                match="canonical request epoch differs from current reconstruction epoch",
            ):
                stale_reconstruction.reconstruct(purpose="execute")

            calls = []
            with pytest.raises(
                CanonicalMaterializationHandleV1Error,
                match="canonical request epoch differs from current materialization epoch|expired",
            ):
                effect_gate.execute(lambda _: calls.append(1))
            assert calls == []
        finally:
            fixture.close_world(world)


def test_one_failed_continuity_reader_fails_all_three_boundaries_closed():
    fixture = _load_materialization_fixture()
    with tempfile.TemporaryDirectory() as directory:
        world = fixture.build_world(directory)
        try:
            handle, _ = world["reconstruct_gate"].reconstruct(purpose="execute")

            def failed_reader():
                raise RuntimeError("continuity unavailable")

            failed = bind_continuity_epoch_authority_v1(
                continuity_id="materialization-galaxy-continuity",
                epoch_reader=failed_reader,
            )
            observer = _observer(world, fixture, failed)
            stale_reconstruction = _fresh_reconstruction_gate(world, fixture, failed)
            effect_gate = CanonicalMaterializationEffectGateV1(
                registry=world["registry"],
                handle=handle,
                request=world["request"],
                proof=world["proof"],
                bound=world["bound"],
                domain_constraint=world["domain_constraint"],
                continuity=failed,
                galaxy=world["galaxy"],
            )

            operations = (
                lambda: observer.render(world["representation"].surface),
                lambda: stale_reconstruction.reconstruct(purpose="execute"),
                lambda: effect_gate.execute(lambda _: b"must-not-run"),
            )
            for operation in operations:
                with pytest.raises(
                    ContinuityEpochAuthorityV1Error,
                    match="read failed closed",
                ):
                    operation()
        finally:
            fixture.close_world(world)


def test_invalid_boolean_epoch_is_rejected_by_shared_continuity():
    continuity = bind_continuity_epoch_authority_v1(
        continuity_id="invalid-runtime-continuity",
        epoch_reader=lambda: True,
    )
    with pytest.raises(ContinuityEpochAuthorityV1Error, match="invalid epoch"):
        continuity.current_epoch()


def test_sanctioned_gate_signatures_expose_continuity_not_raw_epoch_source():
    for gate_type in (
        NyrObservationGateV1,
        RepresentationReconstructionGateV1,
        CanonicalMaterializationEffectGateV1,
    ):
        parameters = inspect.signature(gate_type).parameters
        assert "continuity" in parameters
        assert "epoch_source" not in parameters

    materialization_parameters = inspect.signature(
        CanonicalMaterializationEffectGateV1
    ).parameters
    assert "galaxy" in materialization_parameters
    assert "domain_constraint" in materialization_parameters
