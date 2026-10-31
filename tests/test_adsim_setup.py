"""Check simulator environment exports without Docker or EPICS."""

import csv
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SETUP = Path(__file__).resolve().parents[1] / "docker" / "adsim" / "setup.sh"


class TestADSimEnvironment(unittest.TestCase):
    """Exports preserve existing discovery and are safe to apply repeatedly."""

    def test_additive_exports(self) -> None:
        """Exercise unset lists, gateways, exact duplicates and custom ports."""
        for shell in ("bash", "zsh"):
            if shutil.which(shell) is None:
                continue
            for port in ("6064", "08080"):
                address = f"127.0.0.1:{int(port)}"
                for existing in ("", "gateway:5064 other:5064", f"gateway:5064\t{address}\n"):
                    for automatic in (None, "YES", "NO"):
                        with self.subTest(
                            shell=shell, port=port, existing=existing, auto=automatic
                        ):
                            env = {
                                key: value
                                for key, value in os.environ.items()
                                if not key.startswith("EPICS_CA_")
                            }
                            env.update(ADSIM_CA_PORT=port, SETUP=str(SETUP))
                            commands = subprocess.check_output(
                                ["bash", str(SETUP), "env"], env=env, text=True
                            )
                            # Supply existing values only at evaluation time.
                            env.update(
                                EXPORTS=commands,
                                EPICS_CA_ADDR_LIST=existing,
                                EPICS_CA_NAME_SERVERS=existing,
                                EPICS_CA_MAX_ARRAY_BYTES="20000000",
                            )
                            if automatic is not None:
                                env["EPICS_CA_AUTO_ADDR_LIST"] = automatic
                            result = subprocess.check_output(
                                [
                                    shell,
                                    "-c",
                                    'eval "$EXPORTS"; eval "$EXPORTS"; '
                                    'printf "%s\\0" "$EPICS_CA_ADDR_LIST" '
                                    '"$EPICS_CA_NAME_SERVERS" '
                                    '"${EPICS_CA_AUTO_ADDR_LIST-unset}" '
                                    '"$EPICS_CA_MAX_ARRAY_BYTES"',
                                ],
                                env=env,
                                text=True,
                            ).split("\0")
                            expected = (
                                existing
                                if address in existing.split()
                                else (f"{existing} {address}" if existing else address)
                            )
                            self.assertEqual(
                                result[:4], [expected, expected, automatic or "unset", "20000000"]
                            )

    def test_array_capacity_minimum(self) -> None:
        """Set the required minimum without reducing an existing larger limit."""
        for previous in ("", "1000", "08000000", "10000000", "20000000", "020000000"):
            env = dict(os.environ, EPICS_CA_MAX_ARRAY_BYTES=previous, SETUP=str(SETUP))
            result = subprocess.check_output(
                [
                    "bash",
                    "-c",
                    'eval "$(bash "$SETUP" env)"; printf %s "$EPICS_CA_MAX_ARRAY_BYTES"',
                ],
                env=env,
                text=True,
            )
            expected = previous if int(previous or 0) >= 10000000 else "10000000"
            self.assertEqual(result, expected)

    def test_data_mount_escapes_csv_source(self) -> None:
        """Docker receives a single source field even when the path contains CSV syntax."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            docker = root / "docker"
            docker.write_text(
                '#!/bin/sh\ncase "$1" in\n'
                "  info) exit 0 ;;\n"
                "  container) exit 1 ;;\n"
                '  run) printf "%s\\n" "$@" ;;\n'
                "  *) exit 2 ;;\nesac\n"
            )
            docker.chmod(0o755)
            data = root / 'BEC, "data"'
            env = dict(os.environ, PATH=f"{root}{os.pathsep}{os.environ['PATH']}")
            env.update(ADSIM_DATA_DIR=str(data), ADSIM_SKIP_BUILD="1", ADSIM_CA_PORT="08080")
            output = subprocess.check_output(["bash", str(SETUP), "start"], env=env, text=True)
            args = output.splitlines()
            self.assertIn("EPICS_CA_SERVER_PORT=8080", args)
            self.assertIn("EPICS_CA_REPEATER_PORT=8081", args)
            self.assertIn("127.0.0.1:8080:8080/tcp", args)
            self.assertEqual(
                next(csv.reader([args[args.index("--mount") + 1]])),
                ["type=bind", f"source={data}", "target=/data"],
            )

    def test_invalid_ca_port_is_rejected_before_start(self) -> None:
        for port in ("0", "invalid", "65535", "18446744073709559696"):
            with self.subTest(port=port):
                result = subprocess.run(
                    ["bash", str(SETUP), "start"],
                    env=dict(os.environ, ADSIM_CA_PORT=port),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("ADSIM_CA_PORT must be a decimal port from 1 to 65534", result.stderr)

    def test_ca_cannot_use_internal_zmq_port(self) -> None:
        for action in ("start", "env"):
            with self.subTest(action=action):
                result = subprocess.run(
                    ["bash", str(SETUP), action],
                    env=dict(os.environ, ADSIM_CA_PORT="05555", ADSIM_ZMQ_PORT="5556"),
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("ADSIM_CA_PORT cannot be 5555", result.stderr)


if __name__ == "__main__":
    unittest.main()
