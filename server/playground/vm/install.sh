#!/bin/sh
# Install the Koschei Playground worker on a dedicated Ubuntu 24.04 VM.
#   sudo ./install.sh /path/to/koschei-lang worker-hostname frontend-cidr bind-address
# Example (private network): sudo ./install.sh ~/koschei-lang worker.internal 10.0.0.0/8 10.0.0.5
# Idempotent. Never weakens host-wide settings: no seccomp/AppArmor disabling,
# no sysctl change; the AppArmor grant covers one dedicated bwrap copy only.
set -eu
REPO=${1:?repository checkout}
HOSTNAME_SAN=${2:?worker hostname for the TLS certificate}
PEER_CIDR=${3:?frontend address range allowed to connect}
BIND=${4:?address to listen on}
ROOT=/opt/koschei-worker
ETC=/etc/koschei-worker

[ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 1; }
[ -f /sys/fs/cgroup/cgroup.controllers ] || { echo "cgroup v2 (unified) is required" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required" >&2; exit 1; }

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
if [ ! -s "$ETC/tls-key.pem" ]; then
  # A private CA used only for this worker. The frontend trusts exactly this
  # CA (KOSCHEI_WORKER_CA_FILE) and verifies the hostname.
  (umask 077
   openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 825 \
     -subj "/CN=Koschei worker CA" -keyout "$ETC/ca-key.pem" -out "$ETC/ca-cert.pem" 2>/dev/null
   openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj "/CN=$HOSTNAME_SAN" \
     -keyout "$ETC/tls-key.pem" -out "$ETC/tls.csr" 2>/dev/null
   printf 'subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\n' "$HOSTNAME_SAN" > "$ETC/tls.ext"
   openssl x509 -req -in "$ETC/tls.csr" -CA "$ETC/ca-cert.pem" -CAkey "$ETC/ca-key.pem" \
     -CAcreateserial -days 397 -extfile "$ETC/tls.ext" -out "$ETC/tls-cert.pem" 2>/dev/null
   rm -f "$ETC/tls.csr" "$ETC/tls.ext")
fi
printf 'KOSCHEI_WORKER_BIND=%s\n' "$BIND" > "$ETC/worker.env"
chmod 0600 "$ETC/worker.env"

install -m 0644 "$REPO/server/playground/vm/koschei-worker.service" /etc/systemd/system/koschei-worker.service
install -d -m 0755 /etc/systemd/system/koschei-worker.service.d
printf '[Service]\nIPAddressAllow=%s\n' "$PEER_CIDR" > /etc/systemd/system/koschei-worker.service.d/peer.conf
systemctl daemon-reload
systemctl enable koschei-worker.service >/dev/null
systemctl restart koschei-worker.service
systemctl is-active koschei-worker.service
echo "Frontend trust anchor: $ETC/ca-cert.pem"
