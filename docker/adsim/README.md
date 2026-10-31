# AreaDetector simulator

This Docker image runs a local simDetector IOC at the `BEC:SIM:` PV prefix. It
provides two ROI/Stats chains, image transforms, ADZMQ preview and HDF5 capture.

## Requirements

- A running local Docker engine or Docker Desktop with Linux containers. The
  image uses `linux/amd64`. On Apple Silicon, Docker Desktop must be able to run
  amd64 containers through emulation.
- Network access during the first build to pull the base image and download
  Debian packages and ADZMQ.
- For BEC integration, a local BEC environment and Redis. Install this
  `ophyd_devices` checkout into the Python environment used by the device
  server and use a BEC version with the companion ROI and signal metadata
  interfaces.

## Start the IOC

Run these commands from the repository root:

```bash
bash docker/adsim/setup.sh start
docker logs --tail 30 bec-adsim
docker inspect --format '{{.State.Health.Status}}' bec-adsim
```

Wait for the health status to become `healthy`. The default container is
`bec-adsim` and exposes Channel Access on localhost port 6064 (TCP and UDP)
and ZMQ on localhost port 5555. Acquisition starts idle and BEC can start live
acquisition when the camera connects.

To build separately, run `bash docker/adsim/setup.sh build`. To reuse an
already built image, run `ADSIM_SKIP_BUILD=1 bash docker/adsim/setup.sh start`.
The script refuses to replace a container with the same name.

## Connect a local BEC session

1. To save HDF5 frames, set `ADSIM_DATA_DIR` to the absolute host directory
   containing BEC's output paths **before** starting the IOC. Docker mounts
   that directory at `/data`. With no override, it mounts `docker/adsim/data`.
2. Copy the [example camera config](../../ophyd_devices/configs/ad_camera_example.yaml)
   to a local YAML file, such as `adsim.local.yaml`. Keep the `BEC:SIM:` prefix.
   For HDF5 output, set `deviceConfig.hdf5_path_mapping` to map the same host
   directory from step 1 to `/data`, for example
   `{"/absolute/bec/data": "/data"}`. Set `deviceConfig.save_frame_data: false`
   to run without saving frame files.
3. Start local Redis and the BEC services. Apply the simulator exports in
   the environment that runs `bec-device-server`. For a local tmux setup,
   use `bec-server start --interface tmux` and attach with `bec-server attach`.
   In the device server pane, stop the device server with Ctrl+C and change
   to the `ophyd_devices` repository root. With the BEC environment active,
   restart it directly in that pane:

   ```bash
   adsim_env=$(bash docker/adsim/setup.sh env) &&
     eval "$adsim_env" &&
     bec-device-server
   ```

   If the original device server used a custom service configuration, pass
   the same `--config` path to `bec-device-server`. For a systemd-managed
   device server, apply the generated EPICS values in its service environment
   and restart the service. The exports add the IOC to the existing CA
   discovery lists of the shell where they are evaluated.
4. Run `bec` from the repository root in a second terminal with the BEC
   environment active. At the BEC prompt, add the camera to your local session:

   ```python
   bec.config.add_to_session("./adsim.local.yaml")
   dev.show_all()
   ```

If a default port is occupied, set `ADSIM_CA_PORT` or `ADSIM_ZMQ_PORT` in
the environment. Use distinct host ports and export the same overrides
in the device server pane before running `setup.sh env` there. The CA port
must be in the range 1–65534 and cannot be 5555, which the IOC reserves for
ZMQ even when the host ZMQ port changes.
For a custom ZMQ port, set
`deviceConfig.preview_transports.preview[0].address` in your local YAML to
the URL printed as `ADSIM_ZMQ_ADDRESS`.

## Stop the IOC

```bash
bash docker/adsim/setup.sh stop
```

If you set `ADSIM_CONTAINER` to a custom name, use it again for `stop`.
The command removes the simulator container and keeps files in the mounted
host directory. Run `bash docker/adsim/setup.sh --help` for all options.
