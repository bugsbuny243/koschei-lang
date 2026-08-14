from __future__ import annotations
import unittest
from koschei.event_horizon_isolation_v1 import enter_event_horizon

P="koschei-key-containment"; O="ab"*32; S="session-0001"
I1=b"I"*32; I2=b"J"*32; D1=b"D"*32; D2=b"E"*32

def env(i,d):
    return enter_event_horizon(project_id=P,object_id=O,session_id=S,epoch=17,isolation_key=i,deception_key=d)

class CrossKeyContainmentV1Tests(unittest.TestCase):
    def test_deception_key_cannot_change_identity_domain(self):
        a,b=env(I1,D1),env(I1,D2)
        self.assertEqual(a.universe_id,b.universe_id)
        self.assertEqual(a.shadow_object_id,b.shadow_object_id)
        self.assertEqual(a.gravity_digest,b.gravity_digest)
        self.assertNotEqual(a.content_sha256,b.content_sha256)

    def test_isolation_key_rotates_identity_domain(self):
        a,b=env(I1,D1),env(I2,D1)
        self.assertNotEqual(a.universe_id,b.universe_id)
        self.assertNotEqual(a.shadow_object_id,b.shadow_object_id)
        self.assertNotEqual(a.gravity_digest,b.gravity_digest)

    def test_swapping_key_roles_does_not_reproduce_identity(self):
        a,b=env(I1,D1),env(D1,I1)
        self.assertNotEqual(a.universe_id,b.universe_id)
        self.assertNotEqual(a.shadow_object_id,b.shadow_object_id)

    def test_same_domains_are_deterministic(self):
        self.assertEqual(env(I1,D1),env(I1,D1))

if __name__=="__main__": unittest.main()
