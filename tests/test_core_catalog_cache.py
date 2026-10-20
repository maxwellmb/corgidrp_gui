import json
import os

from corgidrp_gui.core.catalog_cache import (catalog_from_dict, catalog_status, catalog_to_dict,
                                             load_catalog, rebuild_catalog, save_catalog)
from corgidrp_gui.core.steps import MISSING


def test_round_trip_preserves_everything(catalog):
    d = json.loads(json.dumps(catalog_to_dict(catalog)))
    c2 = catalog_from_dict(d)
    assert set(c2.names()) == set(catalog.names())
    for name in catalog.names():
        a, b = catalog.get(name), c2.get(name)
        assert [(x.name, x.default, x.type_str) for x in a.args] == [(x.name, x.default, x.type_str) for x in b.args], name
        assert [(x.param, x.datatypes, x.template_specs) for x in a.calibs] == [(x.param, x.datatypes, x.template_specs) for x in b.calibs], name
        assert a.levels == b.levels and a.predecessors == b.predecessors and a.successors == b.successors
    assert c2.templates == catalog.templates
    # suggestions and warnings work from the cached copy without corgidrp
    names = [s["name"] for s in c2.templates["l1_to_l2b.json"]["steps"]]
    assert c2.suggest_index(names, "flat_division_pol") == catalog.suggest_index(names, "flat_division_pol")


def test_missing_sentinel_survives(catalog):
    d = catalog_to_dict(catalog)
    c2 = catalog_from_dict(json.loads(json.dumps(d)))
    required = [(s.name, a.name) for s in catalog for a in s.args if a.default is MISSING]
    assert required == [(s.name, a.name) for s in c2 for a in s.args if a.default is MISSING]


def test_cache_file_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("CORGIDRP_GUI_HOME", str(tmp_path))
    st = catalog_status(check_corgidrp=False)
    assert not st.exists and "no step catalog" in st.one_line()
    cat = load_catalog()                     # builds and caches
    assert os.path.exists(tmp_path / "step_catalog.json")
    st = catalog_status()
    assert st.exists and st.n_steps == len(cat) and not st.stale, st.one_line()
    assert "built" in st.one_line()
    # tamper with the recorded fingerprint -> reported stale, not rebuilt
    p = tmp_path / "step_catalog.json"
    d = json.loads(p.read_text()); d["meta"]["built_from"]["version"] = "0.0.0"; p.write_text(json.dumps(d))
    st = catalog_status()
    assert st.stale and any("version" in r for r in st.stale_reasons)
    c2 = load_catalog()                      # still loads the (stale) cache
    assert len(c2) == len(cat)
    c3 = rebuild_catalog()
    assert not catalog_status().stale and len(c3) == len(cat)
