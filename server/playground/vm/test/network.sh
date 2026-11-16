#!/bin/sh
# TEST ONLY: worker network isolation on the test VM (run as root).
# 1. No egress from the worker's cgroup (systemd IPAddressDeny=any, cgroup BPF).
# 2. Only the configured peer range may connect to the worker.
set -u
IP=$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | head -1)
CG=/sys/fs/cgroup/system.slice/koschei-worker.service
probe() {  # probe HOST PORT: connect from inside the worker cgroup
  sh -c "echo \$\$ > $CG/cgroup.procs; exec /usr/bin/python3 - $1 $2" <<'PY'
import socket, sys
try:
    socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=5).close()
    print("CONNECTED")
except OSError as error:
    print("BLOCKED", error)
PY
}
connect() {  # connect HOST PORT from outside the worker cgroup
  /usr/bin/python3 - "$1" "$2" <<'PY'
import socket, ssl, sys
try:
    raw = socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=5)
    tls = ssl.create_default_context(cafile="/etc/koschei-worker/ca-cert.pem")
    tls.check_hostname = False
    tls.wrap_socket(raw).close()
    print("TLS_HANDSHAKE_OK")
except (OSError, ssl.SSLError) as error:
    print("BLOCKED", type(error).__name__, error)
PY
}
listening() {  # wait until the worker has passed its preflights and listens
  for _ in $(seq 1 240); do
    ss -Htln "sport = :8443" | grep -q . && return 0
    sleep 1
  done
  return 1
}
echo "egress_public_ip: $(probe 1.1.1.1 443)"
echo "egress_vm_gateway: $(probe 10.0.2.2 22)"

printf 'KOSCHEI_WORKER_BIND=%s\n' "$IP" > /etc/koschei-worker/worker.env
printf '[Service]\nIPAddressAllow=10.0.2.99/32\n' > /etc/systemd/system/koschei-worker.service.d/peer.conf
systemctl daemon-reload; systemctl restart koschei-worker
listening; echo "worker_on_$IP: $(ss -Htln "sport = :8443" | awk '{print $4}')"
echo "peer_not_allowed($IP): $(connect "$IP" 8443)"

printf '[Service]\nIPAddressAllow=%s/32\n' "$IP" > /etc/systemd/system/koschei-worker.service.d/peer.conf
systemctl daemon-reload; systemctl restart koschei-worker; listening
echo "peer_allowed($IP): $(connect "$IP" 8443)"
