"""Regenerate every screenshot in docs/screenshots (run after UI or theme changes)."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
themes = sys.argv[1:] or ["roman", "console", "neon", "homepage"]
for script in ("render_screenshots.py", "render_parser.py", "render_builder.py", "render_console.py", "render_caldb.py"):
    print("==", script)
    subprocess.run([sys.executable, os.path.join(here, script), *themes], check=False)
