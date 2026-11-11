from __future__ import annotations
import unittest
from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.living_synthetic_system_v1 import build_living_synthetic_system
from koschei.synthetic_reality_plane_v1 import build_synthetic_reality

P="koschei-shift-v1"; A="a1"*32; B="b2"*32
I=b"I"*32; D=b"D"*32; G=b"G"*32; S=b"S"*32; R=b"R"*32

def obs(oid, epochs, prefix):
    rows=[]
    for n,e in enumerate(epochs):
        env=enter_event_horizon(project_id=P,object_id=oid,session_id=f"{prefix}-{n:03d}-abcdefgh",epoch=e,isolation_key=I,deception_key=D)
        g=build_shadow_graph(envelope=env,graph_key=G,width=8)
        s=build_living_synthetic_system(graph=g,system_key=S,trace_length=24)
        r=build_synthetic_reality(system=s,graph=g,reality_key=R)
        vals=[x.value for x in r.telemetry]
        rows.append((len(env.content),len(g.nodes),len(g.edges),len(s.services),len(s.packages),len(s.traces),sum(vals)/len(vals)))
    return rows

def shapes(rows): return [x[:6] for x in rows]
def mean(rows): return sum(x[6] for x in rows)/len(rows)

class DistributionShiftObserverV1Tests(unittest.TestCase):
    def test_dense_epoch_window_keeps_shape_parity(self):
        e=list(range(64)); self.assertEqual(shapes(obs(A,e,"dense-a")),shapes(obs(B,e,"dense-b")))
    def test_sparse_epoch_window_keeps_shape_parity(self):
        e=[i*97 for i in range(64)]; self.assertEqual(shapes(obs(A,e,"sparse-a")),shapes(obs(B,e,"sparse-b")))
    def test_reverse_epoch_order_keeps_shape_parity(self):
        e=list(range(63,-1,-1)); self.assertEqual(shapes(obs(A,e,"rev-a")),shapes(obs(B,e,"rev-b")))
    def test_uneven_sample_sizes_keep_mean_close(self):
        a=obs(A,list(range(96)),"long-a"); b=obs(B,list(range(64)),"short-b"); self.assertLess(abs(mean(a)-mean(b)),350)
    def test_session_prefix_length_does_not_change_shape(self):
        e=list(range(48)); a=obs(A,e,"x"); b=obs(B,e,"very-long-observer-prefix"); self.assertEqual(shapes(a),shapes(b))

if __name__=="__main__": unittest.main()
