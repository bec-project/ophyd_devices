#!/usr/bin/env bash
# Reproduce the AD simulator locally; no Python environment or BEC service is modified.
set -euo pipefail

adsim_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
adsim_action="${1:-start}"
adsim_image="${ADSIM_IMAGE:-bec-adsim-zmq:local}"
adsim_name="${ADSIM_CONTAINER:-bec-adsim}"
adsim_ca_port="${ADSIM_CA_PORT:-6064}"
adsim_zmq_port="${ADSIM_ZMQ_PORT:-5555}"
adsim_data_dir="${ADSIM_DATA_DIR:-${adsim_script_dir}/data}"

usage() {
    cat <<'HELP'
Usage: bash docker/adsim/setup.sh [start|build|env|stop]

  start  Build and launch a new simulator; refuse to replace an existing container.
  build  Build the pinned linux/amd64 simulator image (also on Apple Silicon).
  env    Print additive shell exports; apply with: eval "$(bash docker/adsim/setup.sh env)"
  stop   Stop/remove only a container created by this script.

Options are environment variables:
  ADSIM_DATA_DIR    Host directory mounted at /data; default: docker/adsim/data
                   For BEC, point this at its data root and configure
                   hdf5_path_mapping: {"/absolute/bec/data": "/data"} on the camera.
  ADSIM_CONTAINER   Container name, default bec-adsim
  ADSIM_IMAGE       Image tag, default bec-adsim-zmq:local
  ADSIM_CA_PORT     Channel Access TCP/UDP port, default 6064
  ADSIM_ZMQ_PORT    Host ZMQ port, default 5555
  ADSIM_SKIP_BUILD  Set to 1 to start an already-built image.

The IOC exposes BEC:SIM:, two ROI/Stats pairs (2048 samples), Trans1:, image1:,
HDF1: and ZMQ1:. Acquisition starts stopped; BEC's live mode starts it.
Start Docker Desktop before building or launching. All ports bind to localhost.
HELP
}

print_env() {
    # Resolve existing lists when the printed commands are evaluated, not when
    # generated. Keep gateways and automatic discovery, and append only if absent.
    cat <<'ENV'
_adsim_append_address() {
    local variable="$1" address="$2" current
    eval 'current="${'"$variable"'-}"'
    case " $(printf '%s' "$current" | tr '\t\r\n' '   ') " in
        *" $address "*)
            export "$variable=$current"
            return
            ;;
    esac
    export "$variable=${current:+$current }$address"
}
ENV
    printf '_adsim_append_address EPICS_CA_NAME_SERVERS %q\n' "127.0.0.1:${adsim_ca_port}"
    printf '_adsim_append_address EPICS_CA_ADDR_LIST %q\n' "127.0.0.1:${adsim_ca_port}"
    printf 'unset -f _adsim_append_address\n'
    cat <<'ENV'
if [[ -z "${EPICS_CA_MAX_ARRAY_BYTES:-}" ]] ||
    [[ "$EPICS_CA_MAX_ARRAY_BYTES" =~ ^[0-9]+$ && "$EPICS_CA_MAX_ARRAY_BYTES" -lt 10000000 ]]; then
    export EPICS_CA_MAX_ARRAY_BYTES=10000000
fi
ENV
    printf 'export ADSIM_ZMQ_ADDRESS=%q\n' "tcp://127.0.0.1:${adsim_zmq_port}"
}

case "${adsim_action}" in
    -h|--help|help) usage; exit 0 ;;
    env) print_env; exit 0 ;;
    build|start|stop) ;;
    *) usage >&2; exit 2 ;;
esac

command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
docker info >/dev/null

build_image() {
    docker build --platform linux/amd64 --tag "${adsim_image}" "${adsim_script_dir}"
}

case "${adsim_action}" in
    build) build_image ;;
    start)
        if docker container inspect "${adsim_name}" >/dev/null 2>&1; then
            echo "Container ${adsim_name} already exists; choose ADSIM_CONTAINER or stop it explicitly." >&2
            exit 1
        fi
        if [[ "${ADSIM_SKIP_BUILD:-0}" != 1 ]]; then build_image; fi
        mkdir -p -- "${adsim_data_dir}"
        adsim_data_dir="$(cd -- "${adsim_data_dir}" && pwd)"
        docker run --detach --init --interactive --tty --platform linux/amd64 \
            --name "${adsim_name}" --label org.bec-project.adsim=true \
            --env "EPICS_CA_SERVER_PORT=${adsim_ca_port}" \
            --env "EPICS_CA_REPEATER_PORT=$((adsim_ca_port + 1))" \
            --publish "127.0.0.1:${adsim_ca_port}:${adsim_ca_port}/tcp" \
            --publish "127.0.0.1:${adsim_ca_port}:${adsim_ca_port}/udp" \
            --publish "127.0.0.1:${adsim_zmq_port}:5555/tcp" \
            --mount "type=bind,source=${adsim_data_dir},target=/data" \
            "${adsim_image}"
        printf '\nApply these exports in the BEC/device-server shell before starting it:\n'
        print_env
        printf '\nCheck startup with: docker logs %q\n' "${adsim_name}"
        ;;
    stop)
        adsim_owned="$(docker inspect --format '{{index .Config.Labels "org.bec-project.adsim"}}' "${adsim_name}")"
        if [[ "${adsim_owned}" != true ]]; then
            echo "Refusing to stop ${adsim_name}: it was not created by this script." >&2
            exit 1
        fi
        docker stop "${adsim_name}"
        docker rm "${adsim_name}"
        ;;
esac
