import json

from corgidrp_gui.core.recipes import Recipe, RecipeStep, validate_recipe


def test_templates_round_trip(catalog):
    for fname, path in catalog.template_paths.items():
        with open(path) as f:
            original = json.load(f)
        r = Recipe.load(path)
        assert r.to_dict() == original, fname
        assert json.loads(r.to_json()) == original, fname


def test_templates_validate_without_errors(catalog):
    for fname, path in catalog.template_paths.items():
        r = Recipe.load(path)
        start = catalog._template_start_level(fname, r.to_dict())
        errors = [i for i in validate_recipe(r, catalog, start) if i.severity == "error"]
        assert not errors, (fname, [str(e) for e in errors])


def test_validation_catches_bad_recipes(catalog):
    r = Recipe(name="bad", steps=[
        RecipeStep("no_such_step"),
        RecipeStep("frame_select", keywords={"bogus": 1}),
        RecipeStep("convert_to_electrons", calibs={"FlatField": "AUTOMATIC"}),
        RecipeStep("convert_to_electrons", keywords={"k_gain": "x"}),
    ])
    msgs = [str(i) for i in validate_recipe(r, catalog, "L2a")]
    assert any("unknown step" in m for m in msgs)
    assert any("no keyword argument 'bogus'" in m for m in msgs)
    assert any("usually KGain" in m for m in msgs)
    assert any("calibration argument" in m for m in msgs)
    assert any("does not end with a save" in m for m in msgs)


def test_new_step_from_catalog(catalog):
    s = RecipeStep.new(catalog.get("detect_cosmic_rays"))
    assert s.calibs == {"DetectorParams": "AUTOMATIC", "KGain": "AUTOMATIC, OPTIONAL"}
    assert s.keywords and "mode" in s.keywords
    s2 = RecipeStep.new(catalog.get("update_to_l2a"))
    assert s2.calibs is None and s2.keywords is None


def test_editing_and_templating():
    r = Recipe(name="x", inputs=["/a.fits"], outputdir="/out",
               steps=[RecipeStep("a"), RecipeStep("b"), RecipeStep("save")], extra={"RECIPE_SRC": "/p"})
    r.move_step(0, 1)
    assert r.step_names == ["b", "a", "save"]
    t = r.as_template("x_template")
    assert t.template and t.inputs == [] and t.outputdir == "" and "RECIPE_SRC" not in t.extra
    assert r.inputs == ["/a.fits"]   # original untouched
    s = r.steps[0]
    s.set_keyword("k", 1); s.unset_keyword("k")
    assert s.keywords is None
