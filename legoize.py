"""Headless CLI entry point. Run inside Blender:

    blender --background --python legoize.py -- model.obj --studs-wide 15 --out out

All real logic lives in the legoizer package (shared with the add-on UI).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from legoizer import run_cli

if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    run_cli(argv)
