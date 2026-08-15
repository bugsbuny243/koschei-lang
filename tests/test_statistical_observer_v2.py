from __future__ import annotations
import unittest
from koschei.event_horizon_isolation_v1 import enter_event_horizon
from koschei.no_return_shadow_graph_v1 import build_shadow_graph
from koschei.living_synthetic_system_v1 import build_living_synthetic_system
from koschei.synthetic_reality_plane_v1 import build_synthetic_reality

P="koschei-stat-v2"; A="a1"*32; B="b2"*32
I=b"I"*32; D=b"D"*32; G=b"G"*32; S=b"S"*32; R=b"R"*32

def sample(oid, tag):
    rows=[]; vals=[]
    for n in range(256):
        e=enter_event_horizon(project_id=P,object_id=oid,session_id=f"s-{n:03d}-{tag*8}",epoch=n,isolation_key=I,deception_key=D)
        g=build_shadow_graph(envelope=e,graph_key=G,width=8)
        s=build_living_synthetic_system(graph=g,system_key=S,trace_length=24)
        r=build_synthetic_reality(system=s,graph=g,reality_key=R)
        v=[x.value for x in r.telemetry]; q=[x.severity for x in r.incidents]
        vals+=v; rows.append((len(e.content),len(g.nodes),len(g.edges),len(s.services),len(s.packages),len(s.traces),sum(v)/len(v),sum(q)/len(q)))
    return rows,vals

def hist(v):
    h=[0]*10
    for x in v: h[min(x//1000,9)]+=1
    return h

class StatisticalObserverV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.a,c.va=sample(A,"a"); c.b,c.vb=sample(B,"b")
    def test_shape(self):
        self.assertEqual([x[:6] for x in self.a],[x[:6] for x in self.b])
    def test_mean(self):
        self.assertLess(abs(sum(self.va)/len(self.va)-sum(self.vb)/len(self.vb)),200)
    def test_histogram(self):
        self.assertLess(max(abs(x-y)/len(self.va) for x,y in zip(hist(self.va),hist(self.vb))),.015)
    def test_severity(self):
        self.assertLess(abs(sum(x[7] for x in self.a)/256-sum(x[7] for x in self.b)/256),.25)
    def test_range(self):
        self.assertEqual(len(self.va),len(self.vb)); self.assertTrue(all(0<=x<10000 for x in self.va+self.vb))

if __name__=="__main__": unittest.main()
