#!/bin/sh
# TEST ONLY: weaken one protection at a time and require that the worker
# refuses to start. Restores every change. Run as root on the test VM.
set -u
D=/etc/systemd/system/koschei-worker.service.d
fail=0
try() {
  name=$1; shift
  printf '[Service]\n%s\n' "$*" > "$D/zz-degrade.conf"
  systemctl daemon-reload
  systemctl reset-failed koschei-worker.service koschei-worker.socket >/dev/null 2>&1
  systemctl start koschei-worker.socket >/dev/null 2>&1
  timeout 1500 systemctl restart koschei-worker >/dev/null 2>&1
  state=$(systemctl is-active koschei-worker)
  reason=$(journalctl -u koschei-worker -n 40 -o cat --no-pager | grep -E "SandboxUnavailable|ISOLATION DENIED" | tail -1 | cut -c1-160)
  if [ "$state" = active ]; then echo "{\"degrade\":\"$name\",\"refused\":false}"; fail=1
  else echo "{\"degrade\":\"$name\",\"refused\":true,\"reason\":\"$reason\"}"; fi
  systemctl stop koschei-worker >/dev/null 2>&1
  rm -f "$D/zz-degrade.conf"
}
try pids_unlimited "TasksMax=infinity"
try memory_unlimited "MemoryMax=infinity"
try cpu_unlimited "CPUQuota="
try user_namespaces_denied "RestrictNamespaces=~user"
try no_seccomp_no_nnp "SystemCallFilter=
SystemCallArchitectures=
NoNewPrivileges=no
LockPersonality=no
RestrictRealtime=no
RestrictSUIDSGID=no
RestrictNamespaces=no
ProtectClock=no
ProtectKernelModules=no
PrivateDevices=no"
# AppArmor grant removed: the host restriction must then stop bubblewrap.
apparmor_parser -R /etc/apparmor.d/koschei-bwrap
try apparmor_grant_missing ""
apparmor_parser -r /etc/apparmor.d/koschei-bwrap
systemctl daemon-reload
systemctl reset-failed koschei-worker.service koschei-worker.socket >/dev/null 2>&1
systemctl start koschei-worker.socket
timeout 1500 systemctl restart koschei-worker
echo "{\"restored\":\"$(systemctl is-active koschei-worker)\"}"
exit $fail
