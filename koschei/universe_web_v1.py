"""Koschei Universe web shell v1.

Read-only loopback web surface for canonical UniverseProjectionV1 +
UniverseLiveStateV1. Renderer metadata is authority-free. Portal visual state is
derived only from authenticated canonical live events; absence of evidence never
creates activity.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from typing import Callable

from .universe_projection_v1 import UniverseProjectionV1
from .universe_live_state_v1 import UniverseLiveStateV1
from .universe_spatial_layout_v1 import spatial_layout_v1
from .universe_portal_physics_v1 import portal_physics_v1

class UniverseWebError(ValueError): pass

def _hex(v: bytes) -> str: return v.hex()

def universe_payload_v1(*, projection: UniverseProjectionV1, live: UniverseLiveStateV1) -> dict[str, object]:
    if not isinstance(projection, UniverseProjectionV1): raise UniverseWebError("canonical projection required")
    if not isinstance(live, UniverseLiveStateV1): raise UniverseWebError("canonical live state required")
    if live.projection_digest != projection.projection_digest: raise UniverseWebError("live state does not bind this projection")
    if projection.authority or live.authority: raise UniverseWebError("Universe renderer input must be authority-free")
    layout=spatial_layout_v1(projection); portals=portal_physics_v1(projection)
    if layout.authority or portals.authority: raise UniverseWebError("Universe display metadata must be authority-free")
    if layout.projection_digest != projection.projection_digest or portals.projection_digest != projection.projection_digest: raise UniverseWebError("Universe display metadata must bind this projection")
    layout_by_node={n.node_id:n for n in layout.nodes}
    portal_by_edge={(p.source_id,p.destination_id,p.relation,p.evidence_digest):p for p in portals.portals}
    events_by_node={n.node_id:[] for n in projection.nodes}
    kinds_by_node={n.node_id:set() for n in projection.nodes}
    for event in live.events:
        events_by_node[event.node_id].append({"kind":event.event_kind,"epoch":event.epoch,"evidence":_hex(event.evidence_digest)})
        kinds_by_node[event.node_id].add(event.event_kind)
    nodes=[]
    for n in projection.nodes:
        pos=layout_by_node[n.node_id]
        nodes.append({"id":n.node_id,"kind":n.kind,"digest":_hex(n.canonical_digest),"quarantined":n.quarantined,"events":events_by_node[n.node_id],"spatial":{"ring":pos.ring,"angleMicrorad":pos.angle_microrad,"radiusUnits":pos.radius_units,"sizeUnits":pos.size_units}})
    edges=[]
    hard_block={"quarantine","fork","rollback","authority-death","admission-denied"}
    for e in projection.edges:
        p=portal_by_edge[(e.source_id,e.destination_id,e.relation,e.evidence_digest)]
        endpoint_kinds=kinds_by_node[e.source_id] | kinds_by_node[e.destination_id]
        blocked=bool(endpoint_kinds & hard_block)
        active=(not blocked) and ("portal-activity" in endpoint_kinds or "admission-accepted" in endpoint_kinds)
        edges.append({"source":e.source_id,"destination":e.destination_id,"relation":e.relation,"evidence":_hex(e.evidence_digest),"portal":{"style":p.style,"phaseMilli":p.phase_milli,"pulseMilli":p.pulse_milli,"widthMilli":p.width_milli,"active":active,"blocked":blocked}})
    return {"schema":"koschei.universe-web/v1","project":_hex(projection.project_digest),"epoch":projection.epoch,"projection":_hex(projection.projection_digest),"layout":_hex(layout.layout_digest),"portals":_hex(portals.portal_digest),"state":_hex(live.state_digest),"authority":False,"nodes":nodes,"edges":edges}

_HTML=r'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Koschei Universe</title><style>html,body{margin:0;height:100%;background:#030611;color:#dce8ff;font-family:ui-monospace,monospace;overflow:hidden}#c{width:100%;height:100%;display:block}.hud{position:fixed;left:18px;top:16px;background:#07101dcc;border:1px solid #24415e;padding:12px 14px;border-radius:12px}.ok{color:#6fffb0}.bad{color:#ff6f86}</style><canvas id="c"></canvas><div class="hud"><b>KOSCHEI UNIVERSE</b><div id="meta">loading…</div><div id="detail">authority-free observer</div></div><script>
const c=document.getElementById('c'),x=c.getContext('2d'),meta=document.getElementById('meta'),detail=document.getElementById('detail');let S=null,pts=[];function fit(){c.width=innerWidth*devicePixelRatio;c.height=innerHeight*devicePixelRatio;x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);layout()}addEventListener('resize',fit);fit();function layout(){if(!S)return;let cx=innerWidth/2,cy=innerHeight/2,u=Math.min(innerWidth,innerHeight)/1500;pts=S.nodes.map(n=>{let s=n.spatial||{},a=(s.angleMicrorad||0)/1e6,r=(s.radiusUnits||0)*u;return{n,x:cx+Math.cos(a)*r,y:cy+Math.sin(a)*r,r:Math.max(12,(s.sizeUnits||34)*u)}})}function draw(){requestAnimationFrame(draw);x.clearRect(0,0,innerWidth,innerHeight);if(!S)return;let by=Object.fromEntries(pts.map(p=>[p.n.id,p]));for(let e of S.edges){let a=by[e.source],b=by[e.destination],p=e.portal||{};if(!a||!b)continue;x.strokeStyle=p.blocked?'#ff395b99':p.active?'#5de6ffaa':'#6a7ea944';x.lineWidth=Math.max(.8,(p.widthMilli||1000)/1000);x.setLineDash(p.blocked?[2,8]:p.style==='dashed-gate'?[4,5]:[]);x.beginPath();x.moveTo(a.x,a.y);x.lineTo(b.x,b.y);x.stroke();x.setLineDash([])}for(let p of pts){x.fillStyle='#5de6ff44';x.strokeStyle='#5de6ff';x.beginPath();x.arc(p.x,p.y,p.r,0,Math.PI*2);x.fill();x.stroke();x.fillStyle='#e8f2ff';x.textAlign='center';x.fillText(p.n.id,p.x,p.y+p.r+16)}}async function refresh(){try{let r=await fetch('/api/universe',{cache:'no-store'});S=await r.json();meta.innerHTML=`epoch <span class="ok">${S.epoch}</span> · nodes ${S.nodes.length}`;layout()}catch(e){meta.innerHTML='<span class="bad">state unavailable</span>'}}refresh();setInterval(refresh,1500);draw();</script>'''

def serve_universe_v1(provider: Callable[[], tuple[UniverseProjectionV1,UniverseLiveStateV1]], *, host:str="127.0.0.1", port:int=8765)->None:
    try: addr=ipaddress.ip_address(host)
    except ValueError as exc: raise UniverseWebError("host must be a literal loopback address") from exc
    if not addr.is_loopback: raise UniverseWebError("Universe web v1 is loopback-only")
    if not (1<=port<=65535): raise UniverseWebError("invalid port")
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path=="/": body=_HTML.encode(); self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            elif self.path=="/api/universe":
                projection,live=provider(); body=json.dumps(universe_payload_v1(projection=projection,live=live),separators=(",",":"),sort_keys=True).encode(); self.send_response(200); self.send_header("Content-Type","application/json")
            else: self.send_response(404); self.end_headers(); return
            self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self,format,*args): return
    ThreadingHTTPServer((host,port),Handler).serve_forever()
