"""Atalho de desenvolvimento e entrada do PyInstaller: python run.py"""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from dumpbox.launcher import main  # noqa: E402

if __name__ == "__main__":
    main()
