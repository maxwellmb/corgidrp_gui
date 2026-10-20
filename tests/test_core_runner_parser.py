"""End-to-end on real mock data: scan -> group -> recommend -> runner subprocess."""
import json
import os
import subprocess
import sys

from corgidrp_gui.core.parser import build_recipes, group_files, recommend, scan_files
from corgidrp_gui.core.progress import ProgressParser
from corgidrp_gui.core.recipes import Recipe
from corgidrp_gui.backend import LocalBackend


def test_scan_group_recommend(mock_l1_files):
    recs = scan_files(mock_l1_files, LocalBackend())
    assert all(r.ok for r in recs)
    assert recs[0].value("DATALVL") == "L1"
    groups = group_files(recs)
    assert len(groups) == 1
    g = groups[0]
    assert g.label.startswith("L1")
    rec = recommend(g)
    assert rec.ok, rec.error
    assert rec.chains == [["l1_to_l2a_basic.json"]]
    assert "science processing" in rec.reason
    assert any(l.startswith("DATALVL = L1") for l in rec.facts.lines())


def test_build_recipes_from_dict_template(mock_l1_files, tmp_path):
    tpl = {"name": "tiny", "template": True, "drpconfig": {}, "inputs": [], "outputdir": "",
           "steps": [{"name": "discard_setup_frames", "keywords": {"keywords_to_check": ["ISACQ"]}}, {"name": "save"}]}
    chains, log = build_recipes(mock_l1_files, str(tmp_path / "out"), template=tpl)
    assert len(chains) == 1 and len(chains[0]) == 1
    r = chains[0][0]
    assert isinstance(r, Recipe) and r.inputs == mock_l1_files and r.template is False
    assert "Generated Recipe" in log


def test_runner_subprocess_end_to_end(mock_l1_files, tmp_path):
    out = tmp_path / "out"
    recipe = {"name": "tiny", "template": False, "drpconfig": {}, "inputs": mock_l1_files,
              "outputdir": str(out), "steps": [
                  {"name": "discard_setup_frames", "keywords": {"keywords_to_check": ["ISACQ"]}},
                  {"name": "save", "keywords": {"suffix": "gui"}}]}
    rp = tmp_path / "tiny.json"
    rp.write_text(json.dumps(recipe))
    cmd = LocalBackend().runner_command(str(rp))
    assert cmd[0] == sys.executable and "corgidrp_gui.runner" in cmd
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    p = ProgressParser()
    p.feed_text(proc.stdout, "stdout")
    p.feed_text(proc.stderr, "stderr")
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert p.recipe_name == "tiny" and p.total_steps == 2
    assert [s.name for s in p.steps] == ["discard_setup_frames", "save"]
    assert p.finished is True and len(p.outputs) == 2
    assert all(os.path.exists(o) and o.endswith("gui.fits") for o in p.outputs)
    assert any(f.endswith("_recipe.json") for f in os.listdir(out))   # walker saved the recipe copy


def test_runner_reports_failure(tmp_path):
    recipe = {"name": "broken", "template": False, "drpconfig": {}, "inputs": [], "outputdir": str(tmp_path),
              "steps": [{"name": "no_such_step"}]}
    rp = tmp_path / "broken.json"
    rp.write_text(json.dumps(recipe))
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.run(LocalBackend().runner_command(str(rp)), capture_output=True, text=True, env=env, timeout=600)
    p = ProgressParser()
    p.feed_text(proc.stdout); p.feed_text(proc.stderr, "stderr")
    assert proc.returncode == 1
    assert p.finished is False and p.errors and "KeyError" in p.errors[0]
