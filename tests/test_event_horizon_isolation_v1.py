from __future__ import annotations

import inspect
import unittest

from koschei.event_horizon_isolation_v1 import (
    EventHorizonError,
    enter_event_horizon,
    require_canonical_promotion,
)
from koschei.parser import parse


OID = "0123456789abcdef0123456789abcdef"
ISO_KEY = b"i" * 32
DECOY_KEY = b"d" * 32


class EventHorizonIsolationV1Tests(unittest.TestCase):
    def make(self, *, session_id: str = "session-0001", epoch: int = 50):
        return enter_event_horizon(
            project_id="p-void",
            object_id=OID,
            session_id=session_id,
            epoch=epoch,
            isolation_key=ISO_KEY,
            deception_key=DECOY_KEY,
        )

    def test_api_has_no_canonical_reader_capability(self):
        params = inspect.signature(enter_event_horizon).parameters
        self.assertNotIn("canonical_reader", params)
        self.assertNotIn("canonical_source", params)

    def test_same_session_epoch_is_stable(self):
        one = self.make()
        two = self.make()
        self.assertEqual(one, two)

    def test_session_or_epoch_rotates_the_universe(self):
        base = self.make(session_id="session-0001", epoch=50)
        other_session = self.make(session_id="session-0002", epoch=50)
        other_epoch = self.make(session_id="session-0001", epoch=51)
        self.assertNotEqual(base.universe_id, other_session.universe_id)
        self.assertNotEqual(base.shadow_object_id, other_session.shadow_object_id)
        self.assertNotEqual(base.content, other_session.content)
        self.assertNotEqual(base.universe_id, other_epoch.universe_id)
        self.assertNotEqual(base.content, other_epoch.content)

    def test_canonical_identity_never_appears_in_exposed_fields(self):
        envelope = self.make()
        exposed = "|".join([
            envelope.universe_id,
            envelope.shadow_object_id,
            envelope.provenance,
            envelope.content_sha256,
            envelope.gravity_digest,
        ]) + envelope.content.decode("utf-8")
        self.assertNotIn(OID, exposed)
        self.assertFalse(envelope.deployable)
        self.assertEqual(envelope.provenance, "event-horizon-decoy")

    def test_void_source_is_valid_koschei_but_not_canonical(self):
        envelope = self.make()
        program = parse(envelope.content.decode("utf-8"))
        self.assertGreaterEqual(len(program.declarations), 2)
        with self.assertRaises(EventHorizonError):
            require_canonical_promotion(envelope)

    def test_independent_keys_change_the_universe(self):
        one = self.make()
        two = enter_event_horizon(
            project_id="p-void",
            object_id=OID,
            session_id="session-0001",
            epoch=50,
            isolation_key=b"j" * 32,
            deception_key=b"e" * 32,
        )
        self.assertNotEqual(one.universe_id, two.universe_id)
        self.assertNotEqual(one.shadow_object_id, two.shadow_object_id)
        self.assertNotEqual(one.content, two.content)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(EventHorizonError):
            enter_event_horizon(
                project_id="p-void",
                object_id=OID,
                session_id="short",
                epoch=0,
                isolation_key=ISO_KEY,
                deception_key=DECOY_KEY,
            )
        with self.assertRaises(EventHorizonError):
            enter_event_horizon(
                project_id="p-void",
                object_id=OID,
                session_id="session-0001",
                epoch=-1,
                isolation_key=ISO_KEY,
                deception_key=DECOY_KEY,
            )
        with self.assertRaises(EventHorizonError):
            enter_event_horizon(
                project_id="p-void",
                object_id=OID,
                session_id="session-0001",
                epoch=1,
                isolation_key=b"short",
                deception_key=DECOY_KEY,
            )


if __name__ == "__main__":
    unittest.main()
