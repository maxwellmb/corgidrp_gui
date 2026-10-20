"""Run one corgidrp recipe in a plain Python process.

    python -u -m corgidrp_gui.runner RECIPE.json [--inputs-from LIST] [--outputdir DIR] [--pdb]

This is deliberately a thin command around :func:`corgidrp.walker.run_recipe`
so that whatever the GUI runs can also be run, and debugged, from a terminal.
The only additions are a few marker lines on stdout, all prefixed with
``corgidrp_gui ``, which the Status Console parses:

    corgidrp_gui recipe: name=<name> steps=<n> inputs=<m> outputdir=<dir>
    corgidrp_gui output: <path>          (one per file the recipe saved)
    corgidrp_gui finished: status=ok|error elapsed=<seconds> [error=<type>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback


def _say(kind: str, text: str):
    sys.stdout.write(f"corgidrp_gui {kind}: {text}\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="corgidrp_gui.runner", description=__doc__.split("\n\n")[0])
    ap.add_argument("recipe", help="path to a recipe JSON file")
    ap.add_argument("--inputs-from", metavar="LIST", help="text file with one input path per line; replaces the recipe's inputs (used for chained recipes)")
    ap.add_argument("--outputdir", help="override the recipe's outputdir")
    ap.add_argument("--no-save-recipe", action="store_true", help="do not let the walker save a copy of the recipe into outputdir")
    ap.add_argument("--pdb", action="store_true", help="drop into pdb post-mortem on error")
    args = ap.parse_args(argv)

    with open(args.recipe) as f:
        recipe = json.load(f)
    if args.inputs_from:
        with open(args.inputs_from) as f:
            recipe["inputs"] = [l.strip() for l in f if l.strip()]
    if args.outputdir:
        recipe["outputdir"] = args.outputdir
    if recipe.get("outputdir"):
        os.makedirs(recipe["outputdir"], exist_ok=True)

    t0 = time.monotonic()
    _say("recipe", f"name={recipe.get('name', '?')} steps={len(recipe.get('steps', []))} "
                   f"inputs={len(recipe.get('inputs', []))} outputdir={recipe.get('outputdir', '')}")
    try:
        import corgidrp.walker as walker   # imported late so a broken env reports as an error line
        outputs = walker.run_recipe(recipe, save_recipe_file=not args.no_save_recipe)
    except BaseException as exc:          # noqa: BLE001 - we want KeyboardInterrupt reported too
        traceback.print_exc()
        sys.stderr.flush()
        _say("finished", f"status=error elapsed={time.monotonic() - t0:.1f} error={type(exc).__name__}")
        if args.pdb:
            import pdb
            pdb.post_mortem(exc.__traceback__)
        return 1
    for path in outputs or []:
        _say("output", path)
    _say("finished", f"status=ok elapsed={time.monotonic() - t0:.1f} outputs={len(outputs or [])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
