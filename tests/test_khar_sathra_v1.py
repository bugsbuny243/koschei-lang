from dataclasses import replace
import unittest

from koschei.khar_sathra_v1 import (
    KHAR_AXES,
    AxisWitness,
    KharSathraError,
    seal_sathra,
)


def _witnesses(
    *,
    aevra: str = "aevra-1",
    veyra: str = "veyra-bank-a",
    event: str = "event-42",
    reality: str = "reality-7",
    epoch: int = 9,
):
    return tuple(
        AxisWitness(
            axis=axis,
            aevra_digest=aevra,
            veyra_digest=veyra,
            event_digest=event,
            reality_digest=reality,
            epoch=epoch,
            witness_digest=f"witness-{axis}",
        )
        for axis in KHAR_AXES
    )


class KharSathraTests(unittest.TestCase):
    def test_all_six_axes_seal_one_sathra(self) -> None:
        sathra = seal_sathra(_witnesses())
        sathra.assert_sealed()
        self.assertEqual(
            tuple(axis for axis, _ in sathra.axis_witnesses),
            KHAR_AXES,
        )
        self.assertEqual(sathra.veyra_digest, "veyra-bank-a")
        self.assertEqual(sathra.epoch, 9)

    def test_five_of_six_is_zero(self) -> None:
        with self.assertRaisesRegex(KharSathraError, "partial concurrence is zero"):
            seal_sathra(_witnesses()[:-1])

    def test_duplicate_axis_cannot_replace_missing_axis(self) -> None:
        witnesses = list(_witnesses()[:-1])
        witnesses.append(replace(witnesses[0], witness_digest="second-khor"))
        with self.assertRaisesRegex(KharSathraError, "duplicate Khar axis"):
            seal_sathra(witnesses)

    def test_one_witness_cannot_satisfy_two_axes(self) -> None:
        witnesses = list(_witnesses())
        witnesses[1] = replace(
            witnesses[1],
            witness_digest=witnesses[0].witness_digest,
        )
        with self.assertRaisesRegex(KharSathraError, "cannot satisfy more than one"):
            seal_sathra(witnesses)

    def test_cross_aevra_splicing_is_rejected(self) -> None:
        witnesses = list(_witnesses())
        witnesses[2] = replace(witnesses[2], aevra_digest="aevra-2")
        with self.assertRaisesRegex(KharSathraError, "same Aevra"):
            seal_sathra(witnesses)

    def test_cross_veyra_splicing_is_rejected(self) -> None:
        witnesses = list(_witnesses())
        witnesses[3] = replace(witnesses[3], veyra_digest="veyra-bank-b")
        with self.assertRaisesRegex(KharSathraError, "same Veyra"):
            seal_sathra(witnesses)

    def test_cross_event_splicing_is_rejected(self) -> None:
        witnesses = list(_witnesses())
        witnesses[4] = replace(witnesses[4], event_digest="event-99")
        with self.assertRaisesRegex(KharSathraError, "same event"):
            seal_sathra(witnesses)

    def test_cross_reality_splicing_is_rejected(self) -> None:
        witnesses = list(_witnesses())
        witnesses[1] = replace(witnesses[1], reality_digest="reality-8")
        with self.assertRaisesRegex(KharSathraError, "same reality"):
            seal_sathra(witnesses)

    def test_cross_epoch_splicing_is_rejected(self) -> None:
        witnesses = list(_witnesses())
        witnesses[5] = replace(witnesses[5], epoch=10)
        with self.assertRaisesRegex(KharSathraError, "same epoch"):
            seal_sathra(witnesses)

    def test_order_does_not_change_sathra_identity(self) -> None:
        witnesses = _witnesses()
        left = seal_sathra(witnesses)
        right = seal_sathra(reversed(witnesses))
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(left.axis_witnesses, right.axis_witnesses)

    def test_sathra_tamper_fails_closed(self) -> None:
        sathra = seal_sathra(_witnesses())
        tampered = replace(sathra, event_digest="event-tampered")
        with self.assertRaisesRegex(KharSathraError, "seal mismatch"):
            tampered.assert_sealed()


if __name__ == "__main__":
    unittest.main()
