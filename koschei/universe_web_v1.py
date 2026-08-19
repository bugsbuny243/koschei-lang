"""Koschei Universe web shell v1.

Read-only loopback web surface for canonical UniverseProjectionV1 +
UniverseLiveStateV1. The renderer receives digests/status/layout/portal metadata
only and cannot mint or mutate authority.
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


class UniverseWebError(ValueError):
    pass


def _hex(v: bytes) -> str:
    return v.hex()


def universe_payload_v1(*, projection: UniverseProjectionV1,
    live: UniverseLiveStateV1) -> dict[str, object]:
    if not isinstance(projection, UniverseProjectionV1):
        raise UniverseWebError("canonical projection required")
    if not isinstance(live, UniverseLiveStateV1):
        raise UniverseWebError("canonical live state required")
    if live.projection_digest != projection.projection_digest:
        raise UniverseWebError("live state does not bind this projection")
    if projection.authority or live.authority:
        raise UniverseWebError("Universe renderer input must be authority-free")

    layout = spatial_layout_v1(projection)
    portals = portal_physics_v1(projection)
    if layout.authority or portals.authority:
        raise UniverseWebError("Universe display metadata must be authority-free")
    if layout.projection_digest != projection.projection_digest or portals.projection_digest != projection.projection_digest:
        raise UniverseWebError("Universe display metadata must bind this projection")

    layout_by_node = {n.node_id: n for n in layout.nodes}
    portal_by_edge = {
        (p.source_id, p.destination_id, p.relation, p.evidence_digest): p
        for p in portals.portals
    }
    events_by_node: dict[str, list[dict[str, object]]] = {n.node_id: [] for n in projection.nodes}
    for event in live.events:
        events_by_node[event.node_id].append({
            "kind": event.event_kind,
            "epoch": event.epoch,
            "evidence": _hex(event.evidence_digest),
        })

    nodes = []
    for n in projection.nodes:
        pos = layout_by_node[n.node_id]
        nodes.append({
            "id": n.node_id,
            "kind": n.kind,
            "digest": _hex(n.canonical_digest),
            "quarantined": n.quarantined,
            "events": events_by_node[n.node_id],
            "spatial": {
                "ring": pos.ring,
                "angleMicrorad": pos.angle_microrad,
                "radiusUnits": pos.radius_units,
                "sizeUnits": pos.size_units,
            },
        })

    edges = []
    for e in projection.edges:
        p = portal_by_edge[(e.source_id, e.destination_id, e.relation, e.evidence_digest)]
        edges.append({
            "source": e.source_id,
            "destination": e.destination_id,
            "relation": e.relation,
            "evidence": _hex(e.evidence_digest),
            "portal": {
                "style": p.style,
                "phaseMilli": p.phase_milli,
                "pulseMilli": p.pulse_milli,
                "widthMilli": p.width_milli,
            },
        })

    return {
        "schema": "koschei.universe-web/v1",
        "project": _hex(projection.project_digest),
        "epoch": projection.epoch,
        "projection": _hex(projection.projection_digest),
        "layout": _hex(layout.layout_digest),
        "portals": _hex(portals.portal_digest),
        "state": _hex(live.state_digest),
        "authority": False,
        "nodes": nodes,
        "edges": edges,
    }


_HTML = r'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Koschei Universe</title><style>
html,body{margin:0;height:100%;background:#030611;color:#dce8ff;font-family:ui-monospace,monospace;overflow:hidden}#c{width:100%;height:100%;display:block}.hud{position:fixed;left:18px;top:16px;background:#07101dcc;border:1px solid #24415e;padding:12px 14px;border-radius:12px;backdrop-filter:blur(7px)}.hud b{letter-spacing:.16em}.ok{color:#6fffb0}.warn{color:#ffd36f}.bad{color:#ff6f86}#detail{max-width:360px;font-size:12px;margin-top:7px;opacity:.86}</style>
<canvas id="c"></canvas><div class="hud"><b>KOSCHEI UNIVERSE</b><div id="meta">loading canonical state…</div><div id="detail">Read-only authority-free projection</div></div>
<script>
const c=document.getElementById('c'),x=c.getContext('2d'),meta=document.getElementById('meta'),detail=document.getElementById('detail');let S=null,pts=[];
function fit(){c.width=innerWidth*devicePixelRatio;c.height=innerHeight*devicePixelRatio;x.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);layout()}addEventListener('resize',fit);fit();
function status(n){let kinds=new Set(n.events.map(e=>e.kind));if(n.quarantined||kinds.has('fork')||kinds.has('rollback')||kinds.has('quarantine'))return 'bad';if(kinds.has('admission-denied')||kinds.has('budget-block')||kinds.has('authority-death'))return 'warn';return 'ok'}
function layout(){if(!S)return;let cx=innerWidth/2,cy=innerHeight/2,unit=Math.min(innerWidth,innerHeight)/1500;pts=S.nodes.map(n=>{let sp=n.spatial||{},a=(sp.angleMicrorad||0)/1e6,r=(sp.radiusUnits||0)*unit;return{n,x:cx+Math.cos(a)*r,y:cy+Math.sin(a)*r,r:Math.max(12,(sp.sizeUnits||34)*unit)}})}
function draw(){requestAnimationFrame(draw);x.clearRect(0,0,innerWidth,innerHeight);for(let i=0;i<120;i++){let px=(i*97)%innerWidth,py=(i*53)%innerHeight;x.fillStyle='#ffffff20';x.fillRect(px,py,1,1)}if(!S)return;let by=Object.fromEntries(pts.map(p=>[p.n.id,p]));for(let e of S.edges){let a=by[e.source],b=by[e.destination];if(!a||!b)continue;let p=e.portal||{};x.strokeStyle=e.relation==='conduit'?'#5ad9ff80':'#6a7ea955';x.lineWidth=Math.max(.8,(p.widthMilli||1000)/1000);x.setLineDash(p.style==='dashed-gate'?[4,5]:p.style==='simulation-rift'?[2,4]:[]);x.beginPath();x.moveTo(a.x,a.y);x.lineTo(b.x,b.y);x.stroke();x.setLineDash([])}for(let p of pts){let st=status(p.n),col=st==='bad'?'#ff5d78':st==='warn'?'#ffd05d':'#5de6ff';x.shadowColor=col;x.shadowBlur=18;x.fillStyle=col+'55';x.beginPath();x.arc(p.x,p.y,p.r,0,Math.PI*2);x.fill();x.shadowBlur=0;x.strokeStyle=col;x.stroke();x.fillStyle='#e8f2ff';x.textAlign='center';x.font='12px ui-monospace';x.fillText(p.n.id,p.x,p.y+p.r+18)}}
c.addEventListener('click',ev=>{let p=pts.find(p=>Math.hypot(ev.clientX-p.x,ev.clientY-p.y)<=p.r+8);if(!p)return;detail.textContent=`${p.n.id} · ${p.n.kind} · ${status(p.n)} · events: ${p.n.events.map(e=>e.kind).join(', ')||'none'}`});
async function refresh(){try{let r=await fetch('/api/universe',{cache:'no-store'});S=await r.json();meta.innerHTML=`epoch <span class="ok">${S.epoch}</span> · nodes ${S.nodes.length} · authority ${S.authority}`;layout()}catch(e){meta.innerHTML='<span class="bad">state unavailable</span>'}}refresh();setInterval(refresh,1500);draw();</script>'''


def serve_universe_v1(provider: Callable[[], tuple[UniverseProjectionV1, UniverseLiveStateV1]], *,
    host: str = "127.0.0.1", port: int = 8765) -> None:
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as exc:
        raise UniverseWebError("host must be a literal loopback address") from exc
    if not addr.is_loopback:
        raise UniverseWebError("Universe web v1 is loopback-only")
    if not (1 <= port <= 65535):
        raise UniverseWebError("invalid port")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = _HTML.encode()
                self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            elif self.path == "/api/universe":
                projection, live = provider()
                body = json.dumps(universe_payload_v1(projection=projection, live=live), separators=(",",":"), sort_keys=True).encode()
                self.send_response(200); self.send_header("Content-Type","application/json")
            else:
                self.send_response(404); self.end_headers(); return
            self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, format, *args):
            return

    ThreadingHTTPServer((host, port), Handler).serve_forever()
