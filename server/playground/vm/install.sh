#!/bin/sh
# Install the Koschei Playground worker on a dedicated Ubuntu 24.04 VM.
#
#   sudo ./install.sh REPO NAMES LISTEN INGRESS...
#
#   REPO     path of a koschei-lang checkout
#   NAMES    comma-separated DNS names / IPs for the TLS certificate
#   LISTEN   address:port of the listening socket, e.g. 0.0.0.0:8443
#   INGRESS  who may open a connection: one or more CIDRs, or the single
#            word "any" when the frontend's address is not fixed (Railway
#            without static egress IPs)
#
# Examples:
#   sudo ./install.sh ~/koschei-lang worker.example.com 0.0.0.0:8443 any
#   sudo ./install.sh ~/koschei-lang worker.example.com 0.0.0.0:8443 203.0.113.7/32
#
# Ingress and egress are separate units on purpose. INGRESS is applied to
# koschei-worker.socket only. The worker service keeps IPAddressDeny=any
# (loopback excepted) for every connection it opens itself, so INGRESS=any
# never lets the worker or a submitted program reach the Internet or a
# private network. The install verifies that and stops otherwise.
#
# Idempotent. Never weakens host-wide settings: no seccomp/AppArmor disabling,
# no sysctl change; the AppArmor grant covers one dedicated bwrap copy only.
set -eu
REPO=${1:?repository checkout}
NAMES=${2:?worker DNS names for the TLS certificate (comma-separated)}
LISTEN=${3:?listen address:port, e.g. 0.0.0.0:8443}
shift 3
[ $# -ge 1 ] || { echo "INGRESS: give CIDRs or the word any" >&2; exit 2; }
ROOT=/opt/koschei-worker
ETC=/etc/koschei-worker
UNITS=/etc/systemd/system

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -f /sys/fs/cgroup/cgroup.controllers ] || { echo "cgroup v2 (unified) is required" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required" >&2; exit 1; }

# Validate everything before changing the system.
INGRESS=$(python3 - "$LISTEN" "$NAMES" "$@" <<'PY'
import ipaddress, re, sys
listen, names, *ingress = sys.argv[1:]
host, sep, port = listen.rpartition(":")
host = host.strip("[]")
if not sep or not port.isdigit() or not 0 < int(port) < 65536:
    sys.exit("LISTEN must be address:port")
ipaddress.ip_address(host)
for name in names.split(","):
    try:
        ipaddress.ip_address(name)
    except ValueError:
        if not re.fullmatch(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.?)+", name, re.I):
            sys.exit("bad certificate name: " + name)
if ingress == ["any"]:
    print("any")
else:
    if "any" in ingress:
        sys.exit("'any' cannot be combined with ranges")
    print(" ".join(str(ipaddress.ip_network(c, strict=True)) for c in ingress))
PY
)
SAN=$(python3 - "$NAMES" <<'PY'
import ipaddress, sys
out = []
for name in sys.argv[1].split(","):
    try:
        ipaddress.ip_address(name)
        out.append("IP:" + name)
    except ValueError:
        out.append("DNS:" + name)
print(",".join(out))
PY
)
CN=${NAMES%%,*}

apt-get install -y -q bubblewrap python3-venv openssl >/dev/null
id koschei-worker >/dev/null 2>&1 || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin koschei-worker

install -d -o root -g root -m 0755 "$ROOT" "$ROOT/bin"
install -o root -g koschei-worker -m 0750 /usr/bin/bwrap "$ROOT/bin/bwrap"
[ -d "$ROOT/venv" ] || python3 -m venv "$ROOT/venv"
"$ROOT/venv/bin/pip" install -q --no-cache-dir "$REPO"
rm -rf "$ROOT/playground"
install -d -o root -g root -m 0755 "$ROOT/playground"
cp "$REPO/server/playground/app.py" "$REPO/server/playground/worker.py" \
   "$REPO/server/playground/runtime_security_probe.py" "$REPO/server/playground/index.html" "$ROOT/playground/"
chmod 0644 "$ROOT/playground/"*

if [ -d /etc/apparmor.d ] && command -v apparmor_parser >/dev/null; then
  install -m 0644 "$REPO/server/playground/vm/koschei-bwrap.apparmor" /etc/apparmor.d/koschei-bwrap
  apparmor_parser -r /etc/apparmor.d/koschei-bwrap
fi

install -d -o root -g root -m 0700 "$ETC"
if [ ! -s "$ETC/worker-token" ]; then
  (umask 077; openssl rand -hex 32 > "$ETC/worker-token")
fi
sh "$REPO/server/playground/vm/make-certs.sh" "$ETC" "$SAN" "$CN"
[ -f "$ETC/worker.env" ] || install -m 0600 /dev/null "$ETC/worker.env"
# Older installs bound the service itself; the socket unit owns that now.
sed -i '/^KOSCHEI_WORKER_BIND=/d' "$ETC/worker.env"

install -m 0644 "$REPO/server/playground/vm/koschei-worker.service" "$UNITS/koschei-worker.service"
install -m 0644 "$REPO/server/playground/vm/koschei-worker.socket" "$UNITS/koschei-worker.socket"
# An older install allowed the frontend range on the *service*, which also
# opened egress to it. Remove it so the service is loopback-only again.
rm -f "$UNITS/koschei-worker.service.d/peer.conf"
install -d -m 0755 "$UNITS/koschei-worker.socket.d"
{
  printf '[Socket]\nListenStream=\nListenStream=%s\n' "$LISTEN"
  printf 'IPAddressAllow=%s\n' "$INGRESS"
} > "$UNITS/koschei-worker.socket.d/ingress.conf"
systemctl daemon-reload

# Refuse a configuration in which the worker process could open connections
# beyond loopback, whatever drop-ins exist on this machine.
allow=$(systemctl show -p IPAddressAllow --value koschei-worker.service)
deny=$(systemctl show -p IPAddressDeny --value koschei-worker.service)
python3 - "$allow" "$deny" <<'PY' || { echo "worker egress is not loopback-only; refusing" >&2; exit 1; }
import ipaddress, sys
allow, deny = sys.argv[1].split(), sys.argv[2].split()
nets = [ipaddress.ip_network(a, strict=False) for a in allow]
assert all(n.is_loopback for n in nets), allow
assert {"0.0.0.0/0", "::/0"} <= set(deny), deny
PY

systemctl enable koschei-worker.socket koschei-worker.service >/dev/null
systemctl stop koschei-worker.service koschei-worker.socket 2>/dev/null || true
systemctl reset-failed koschei-worker.service koschei-worker.socket 2>/dev/null || true
systemctl start koschei-worker.socket
systemctl start koschei-worker.service
systemctl is-active koschei-worker.socket koschei-worker.service

# Frontend settings, readable by root only. Copy these three values into the
# frontend's secret variables; never paste the token into chat or tickets.
PORT=${LISTEN##*:}
(umask 077
 {
   printf 'KOSCHEI_WORKER_URL=https://%s:%s\n' "$CN" "$PORT"
   printf 'KOSCHEI_WORKER_TOKEN=%s\n' "$(cat "$ETC/worker-token")"
   printf 'KOSCHEI_WORKER_CA_PEM="%s"\n' "$(cat "$ETC/ca-cert.pem")"
 } > "$ETC/frontend.env")
echo "Ingress allowed from: $INGRESS (worker egress: loopback only)"
echo "Frontend settings: $ETC/frontend.env (root only)"
