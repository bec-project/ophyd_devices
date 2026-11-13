#!/bin/sh
set -eu

# libca otherwise forks caRepeater after the IOC has created ZeroMQ threads.
# That sequence can deadlock under Rosetta. Start it first and wait for its port.
/opt/base/bin/linux-x86_64/caRepeater &
repeater_pid=$!
repeater_port=$(printf '%04X' "${EPICS_CA_REPEATER_PORT:-5065}")
attempt=0
while [ "$attempt" -lt 100 ]; do
    if awk -v port=":$repeater_port" '$2 ~ port "$" { found=1 } END { exit !found }' /proc/net/udp /proc/net/udp6; then
        exec "$@"
    fi
    kill -0 "$repeater_pid" 2>/dev/null || { echo 'caRepeater exited before binding' >&2; exit 1; }
    attempt=$((attempt + 1))
    sleep 0.05
done
echo 'Timed out waiting for caRepeater' >&2
exit 1
