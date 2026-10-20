import subprocess
import sys


def test_version_and_help():
    out = subprocess.run([sys.executable, "-m", "corgidrp_gui.app", "--version"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "corgidrp_gui 0.1.0" in out.stdout + out.stderr
    out = subprocess.run([sys.executable, "-m", "corgidrp_gui.app", "--help"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--tool" in out.stdout and "--queue" in out.stdout
    out = subprocess.run([sys.executable, "-m", "corgidrp_gui.runner", "--help"], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and "--inputs-from" in out.stdout


def test_parse_args():
    from corgidrp_gui.app import parse_args
    a = parse_args(["--tool", "parser", "--tool", "console", "--files", "a.fits", "b.fits", "--theme", "neon"])
    assert a.tool == ["parser", "console"] and a.files == ["a.fits", "b.fits"] and a.theme == "neon"
