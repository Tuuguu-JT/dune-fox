#!/usr/bin/env python3
"""Backward-compatible CLI entry. Prefer: python -m dune_fox.cli"""

from dune_fox.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
