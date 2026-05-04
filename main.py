"""Hyperliquid Outcomes Paper Trading — CLI entry point.

Quick-start entrypoint that runs a demonstration simulation using
synthetic market data and the built-in InventorySkewMM strategy.

Usage::

    python main.py
    python main.py --trades 5000 --log-level DEBUG
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "examples"))

from examples.run_simulation import main

if __name__ == "__main__":
    main()
