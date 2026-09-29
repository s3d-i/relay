#!/usr/bin/env python3
"""Resolve the source checkout through a symlinked skill; no pip install required."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from research_relay.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
