"""Koschei Planetary Security Console v1.

A zero-dependency backend+frontend observability surface for the six convergence
domains. This is presentation and read-only inspection only: it cannot mint or
change authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Final


@dataclass(frozen=True, slots=True)
class PlanetV1:
    id: str
    name: str
    domain: str
    role: str
    invariant: str
    orbit: int
    radius: int


PLANETS: Final[tuple[PlanetV1, ...]] = (
    PlanetV1("origin", "ORIGIN", "identity/provenance", "pins source, artifact, revision, policy and epoch", "identity must be canonical before policy", 92, 15),
    PlanetV1("aegis", "AEGIS", "authority", "contains exact effects and targets", "no ambient authority; widening requires admission", 138, 18),
    PlanetV1("forge", "FORGE", "integrity", "binds source -> Object Space -> Native IR -> artifact", "integrity drift fails closed", 187, 21),
    PlanetV1("pulse", "PULSE", "behavior", "tracks effect, target and resource drift", "new behavior is evidence, never automatic authority", 242, 17),
    PlanetV1("oracle", "ORACLE", "evidence/prediction", "exposes deterministic facts to Sentinel", "observation never implies control", 296, 23),
    PlanetV1("epoch", "EPOCH", "recovery/time", "leases, epochs, revocation and fresh proof", "compromised authority is never silently resurrected", 354, 20),
)


def universe_payload_v1() -> dict[str, object]:
    return {
        "schema": "koschei.planetary-console.v1",
        "center": {
            "name": "KOSCHEI CORE",
            "role": "deterministic admission",
            "law": "all mandatory domains must agree on the same canonical reality",
        },
        "planets": [asdict(item) for item in PLANETS],
        "sentinel": {
            "name": "SENTINEL",
            "role": "observe/classify/explain/recommend restriction/request quarantine",
            "authority": False,
        },
    }


HTML: Final[str] = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Koschei Reality System</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#02030a;color:#eef;font-family:ui-monospace,Consolas,monospace}canvas{position:fixed;inset:0}.hud{position:fixed;left:24px;top:22px;z-index:2;letter-spacing:.14em}.hud b{font-size:18px}.hud small{display:block;opacity:.55;margin-top:7px}.panel{position:fixed;right:24px;top:24px;width:min(360px,42vw);padding:18px;border:1px solid #ffffff24;border-radius:18px;background:#050817cc;backdrop-filter:blur(16px);box-shadow:0 0 60px #4050ff18}.panel h2{margin:0 0 8px}.tag{display:inline-block;padding:4px 8px;border:1px solid #ffffff22;border-radius:99px;font-size:11px;opacity:.8}.panel p{line-height:1.55;opacity:.78}.law{margin-top:12px;padding:12px;border-left:2px solid #9ef;background:#9ef1}.bottom{position:fixed;left:24px;bottom:22px;opacity:.55;font-size:11px;letter-spacing:.12em}
</style>
<canvas id="c"></canvas><div class="hud"><b>KOSCHEI // REALITY SYSTEM</b><small>DETERMINISTIC SECURITY CONVERGENCE</small></div><aside class="panel" id="panel"><h2>KOSCHEI CORE</h2><span class="tag">DETERMINISTIC ADMISSION</span><p>Click a planet. Every world is a real security domain, not decoration.</p><div class="law">No planet can manufacture authority by itself.</div></aside><div class="bottom">SENTINEL OBSERVES THE SYSTEM. THE COMPILER/RUNTIME OWNS FINAL AUTHORITY.</div>
<script>
const c=document.getElementById('c'),x=c.getContext('2d'),p=document.getElementById('panel');let W,H,D,sys,pts=[];
function fit(){D=devicePixelRatio||1;W=innerWidth;H=innerHeight;c.width=W*D;c.height=H*D;c.style.width=W+'px';c.style.height=H+'px';x.setTransform(D,0,0,D,0,0)}addEventListener('resize',fit);fit();
fetch('/api/universe').then(r=>r.json()).then(j=>sys=j);
const stars=Array.from({length:260},()=>[Math.random(),Math.random(),Math.random()*1.6+.2,Math.random()*.7+.15]);
function draw(t){x.clearRect(0,0,W,H);for(const s of stars){x.globalAlpha=s[3];x.fillStyle='#fff';x.fillRect(s[0]*W,s[1]*H,s[2],s[2])}x.globalAlpha=1;if(!sys){requestAnimationFrame(draw);return}
 const cx=W*.43,cy=H*.53,scale=Math.min(W,H)/780;pts=[];
 const g=x.createRadialGradient(cx,cy,4,cx,cy,56*scale);g.addColorStop(0,'#fff');g.addColorStop(.12,'#c8f7ff');g.addColorStop(.45,'#495dff');g.addColorStop(1,'#17204a00');x.fillStyle=g;x.beginPath();x.arc(cx,cy,60*scale,0,7);x.fill();
 x.fillStyle='#fff';x.font=`${12*scale+8}px ui-monospace`;x.textAlign='center';x.fillText('KOSCHEI',cx,cy+4);
 sys.planets.forEach((q,i)=>{let o=q.orbit*scale;x.strokeStyle='#7d8cff22';x.lineWidth=1;x.beginPath();x.arc(cx,cy,o,0,7);x.stroke();let a=t*.00008*(1+i*.11)+i*1.03,px=cx+Math.cos(a)*o,py=cy+Math.sin(a)*o*.54;let r=q.radius*scale;
  let gr=x.createRadialGradient(px-r*.35,py-r*.4,2,px,py,r*1.2);gr.addColorStop(0,['#d8ffff','#b5c8ff','#f9c4ff','#9fffc8','#ffd3a6','#e0b7ff'][i]);gr.addColorStop(.55,['#36d9ff','#5d71ff','#d84cff','#20c977','#ff7d3d','#8e5bff'][i]);gr.addColorStop(1,'#060716');x.fillStyle=gr;x.shadowBlur=25;x.shadowColor=['#36d9ff','#5d71ff','#d84cff','#20c977','#ff7d3d','#8e5bff'][i];x.beginPath();x.arc(px,py,r,0,7);x.fill();x.shadowBlur=0;x.fillStyle='#ffffffcc';x.font='11px ui-monospace';x.fillText(q.name,px,py+r+16);pts.push([px,py,r+10,q]); });requestAnimationFrame(draw)}requestAnimationFrame(draw);
c.addEventListener('click',e=>{for(const a of pts){let dx=e.clientX-a[0],dy=e.clientY-a[1];if(dx*dx+dy*dy<a[2]*a[2]){let q=a[3];p.innerHTML=`<h2>${q.name}</h2><span class="tag">${q.domain.toUpperCase()}</span><p>${q.role}</p><div class="law">${q.invariant}</div>`;break}}});
</script></html>'''


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/universe":
            raw = json.dumps(universe_payload_v1(), separators=(",", ":")).encode()
            self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        if self.path == "/" or self.path.startswith("/?"):
            raw = HTML.encode()
            self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.send_header("content-length", str(len(raw))); self.end_headers(); self.wfile.write(raw); return
        self.send_error(404)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve_planetary_console_v1(host: str = "127.0.0.1", port: int = 8787) -> None:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("planetary console v1 is loopback-only")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("invalid port")
    ThreadingHTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    serve_planetary_console_v1()
