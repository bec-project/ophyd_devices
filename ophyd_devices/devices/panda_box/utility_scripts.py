# pragma: no cover # We skip these utility scripts in the coverage report.
"""
Module with utility scripts to run on the PandaBox device.

- Save the PandaBox layout to a local file on disk.
  Example usage: python ./utility_scripts.py --host panda-box-host.psi.ch --save-layout ./my_layout.ini
- Load a PandaBox layout from a local file on disk.
  Example usage: python ./utility_scripts.py --host panda-box-host.psi.ch --load-layout ./my_layout.ini

"""

import argparse
from pathlib import Path

from ophyd_devices.devices.panda_box.panda_box import (
    load_layout_from_file_to_panda,
    save_panda_layout_to_file,
)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load or save a PandaBox layout")

    parser.add_argument("--host", type=str, required=True, help="Hostname of the PandaBox")

    group = parser.add_mutually_exclusive_group(required=True)

    group.add_argument(
        "--save-layout", type=Path, metavar="FILE", help="Save current PandaBox layout to FILE"
    )

    group.add_argument(
        "--load-layout", type=Path, metavar="FILE", help="Load PandaBox layout from FILE"
    )

    return parser


def main() -> None:
    """Main entry point for the utility script."""
    parser = build_argparser()
    args = parser.parse_args()

    if args.save_layout is not None:
        save_panda_layout_to_file(host=args.host, file_path=args.save_layout)

    elif args.load_layout is not None:
        load_layout_from_file_to_panda(host=args.host, file_path=args.load_layout)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
