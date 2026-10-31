"""Check simulator environment exports without Docker or EPICS."""

import os
import shutil
import subprocess
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
            for port in ("6064", "7064"):
                address = f"127.0.0.1:{port}"
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
        for previous in ("", "1000", "10000000", "20000000"):
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
            self.assertEqual(result, str(max(int(previous or 0), 10000000)))


if __name__ == "__main__":
    unittest.main()
