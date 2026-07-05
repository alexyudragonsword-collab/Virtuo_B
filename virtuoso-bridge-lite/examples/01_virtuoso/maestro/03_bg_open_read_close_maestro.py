#!/usr/bin/env python3
"""Open a maestro in background, read basic session config, then close it.

Usage::

    python 03_bg_open_read_close_maestro.py <LIB> <CELL>

    Both arguments are required.  Example::

        python 03_bg_open_read_close_maestro.py PLAYGROUND_AMP TB_AMP_5T_D2S_DC_AC

    Running this script from VSCode without passing the args will NOT work.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from virtuoso_bridge import VirtuosoClient
from virtuoso_bridge.virtuoso.maestro import close_session, open_session


def _first_element(raw: str | None) -> str:
    """Extract the first quoted string from a SKILL list like (\"name\")."""
    m = re.search(r'"([^"]+)"', raw or "")
    return m.group(1) if m else ""


def main() -> int:
    if len(sys.argv) < 3:
        print("=" * 60, file=sys.stderr)
        print(" ERROR: missing required arguments <LIB> <CELL>", file=sys.stderr)
        print()
        print(
            f" Usage: python {Path(__file__).name} <LIB> <CELL>\n"
            " Example: python 03_bg_open_read_close_maestro.py PLAYGROUND_AMP TB_AMP_5T_D2S_DC_AC\n",
            file=sys.stderr,
        )
        print(
            " NOTE: Running this script from VSCode (Ctrl+F5 / F5) will NOT\n"
            "       work — VSCode does not pass command-line arguments by default.\n",
            file=sys.stderr,
        )
        print("=" * 60, file=sys.stderr)
        return 1

    lib, cell = sys.argv[1], sys.argv[2]
    client = VirtuosoClient.from_env()

    # Open background session — raises RuntimeError if the cell or view is missing
    try:
        session = open_session(client, lib, cell)
    except RuntimeError as exc:
        print(f"[ERROR] Failed to open maestro: {exc}", file=sys.stderr)
        print(
            "  Verify that:\n"
            f"    1. Library '{lib}' exists in Virtuoso\n"
            f"    2. Cell '{cell}' exists in '{lib}'\n"
            f"    3. Cell '{cell}' has a 'maestro' view\n",
            file=sys.stderr,
        )
        return 1

    # Clean up regardless of whether reading succeeds
    error: BaseException | None = None
    try:
        cfg: dict[str, str] = {"session": session}
        test = _first_element(
            client.execute_skill(
                f'maeGetSetup(?session "{session}")', timeout=15
            ).output
        )
        cfg["test"] = test or "(none)"
        cfg["lib"] = lib
        cfg["cell"] = cell
        print(json.dumps(cfg, indent=2, default=str))
    except Exception as exc:
        error = exc
        print(f"[ERROR] Reading session config failed: {exc}", file=sys.stderr)
    finally:
        # close_session failure should not mask the original error
        try:
            close_session(client, session)
        except Exception as close_exc:
            print(f"[WARN] Failed to close session cleanly: {close_exc}", file=sys.stderr)
            if error is None:
                error = close_exc

    if error is not None:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
