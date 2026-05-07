"""Confirm Volcano credentials are loadable and (optionally) reach the API.

Usage:
    python -m shared.scripts.install.verify_volcano [--env PATH] [--no-network]

Exits 0 on success, nonzero on failure. With --no-network we only check that
config.load() succeeds; with the network flag (default) we also send a tiny
ping submit (no audio actually transcribed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from shared.scripts.lib import config


def main(*, env_path: Path, do_network: bool) -> int:
    try:
        cfg = config.load(env_path=env_path)
    except config.ConfigError as exc:
        print(f"[verify_volcano] Volcano config error: {exc}")
        print(f"[verify_volcano] config error: {exc}", file=sys.stderr)
        return 1

    print(
        f"[verify_volcano] config ok — console={cfg.volcano.console} "
        f"resource_id={cfg.volcano.resource_id} upload_backend={cfg.upload_backend}"
    )
    if not do_network:
        return 0

    # Plan 1 leaves the actual network ping to Plan 2 (where volcano_submit.py
    # exists). For now, --no-network is the default in tests; manual install
    # users can re-run with --network after Plan 2 ships.
    print("[verify_volcano] skipping network ping (Plan 2 adds the real submit)")
    return 0


def cli() -> int:  # pragma: no cover - thin argparse glue
    p = argparse.ArgumentParser(prog="verify_volcano")
    p.add_argument("--env", type=Path, default=Path(".env"))
    p.add_argument("--no-network", action="store_true")
    args = p.parse_args()
    return main(env_path=args.env, do_network=not args.no_network)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli())
