import inspect

from corgidrp_gui.core.steps import SAVE_STEP_NAME, parse_google_args


def test_catalog_covers_all_steps(catalog):
    import corgidrp.walker as walker
    assert set(walker.all_steps) <= set(catalog.names())
    assert SAVE_STEP_NAME in catalog
    assert len(catalog.templates) >= 70


def test_every_step_has_summary_and_source(catalog):
    for info in catalog:
        assert info.summary, info.name
        if info.name != SAVE_STEP_NAME:
            assert info.source_file.endswith(".py"), info.name
            assert info.category != "Other", (info.name, info.module)


def test_template_calibs_map_to_slots_in_order(catalog):
    for fname, tpl in catalog.templates.items():
        for step in tpl["steps"]:
            info = catalog.get(step["name"])
            assert info is not None, (fname, step["name"])
            for j, label in enumerate(step.get("calibs") or {}):
                assert j < len(info.calibs), (fname, step["name"], label)
                assert label in info.calibs[j].datatypes, (fname, step["name"], label, info.calibs[j])


def test_template_keywords_are_real_arguments(catalog):
    for fname, tpl in catalog.templates.items():
        for step in tpl["steps"]:
            info = catalog.get(step["name"])
            for k in step.get("keywords") or {}:
                assert info.arg(k) is not None or info.accepts_var_kwargs, (fname, step["name"], k)


def test_calib_params_are_not_listed_as_keyword_args(catalog):
    for info in catalog:
        calib_names = {c.param for c in info.calibs}
        assert calib_names.isdisjoint(a.name for a in info.args), info.name


def test_defaults_come_from_signature(catalog):
    fs = catalog.get("frame_select")
    assert fs.arg("bpix_frac").default == 1.0
    assert fs.arg("discard_bad").default is True
    assert fs.arg("bpix_frac").type_str == "float"
    assert "fraction" in fs.arg("bpix_frac").description


def test_known_calib_slots(catalog):
    dcr = catalog.get("detect_cosmic_rays")
    assert [c.label for c in dcr.calibs] == ["DetectorParams", "KGain"]
    assert dcr.calibs[1].optional_in_templates
    assert not dcr.calibs[0].optional_in_templates
    bp = catalog.get("create_bad_pixel_map")
    assert set(bp.calibs[0].datatypes) == {"Dark", "DetectorNoiseMaps"}


def test_levels_and_categories(catalog):
    assert "L1" in catalog.get("prescan_biassub").levels
    assert catalog.get("flat_division").levels[0] == "L2a"
    assert catalog.get("do_psf_subtraction").levels == ("L3",)
    cats = catalog.by_category()
    assert list(cats)[:4] == ["L1 → L2a", "L2a → L2b", "L2b → L3", "L3 → L4"]
    assert sum(len(v) for v in cats.values()) == len(catalog)


def test_suggest_index_uses_templates(catalog):
    names = [s["name"] for s in catalog.templates["l1_to_l2b.json"]["steps"]]
    idx, reason = catalog.suggest_index(names, "flat_division_pol")
    assert names[idx - 1] == "cti_correction", (idx, reason)
    idx, reason = catalog.suggest_index([], "prescan_biassub")
    assert idx == 0
    # a step with no template history lands before the trailing save
    idx, reason = catalog.suggest_index(["prescan_biassub", "save"], "northup")
    assert 0 <= idx <= 2


def test_order_warnings_quiet_on_templates(catalog):
    for fname, tpl in catalog.templates.items():
        names = [s["name"] for s in tpl["steps"]]
        start = catalog._template_start_level(fname, tpl)
        level_warnings = [m for _, m in catalog.order_warnings(names, start) if "frames here are" in m]
        assert not level_warnings, (fname, level_warnings)


def test_order_warnings_fire(catalog):
    w = catalog.order_warnings(["flat_division", "prescan_biassub"], "L1")
    assert any("frames here are L1" in m for _, m in w)
    assert any("does not end with a save" in m for _, m in w)


def test_parse_google_args_handles_continuations():
    doc = """Do a thing.

    Longer description.

    Args:
        input_dataset (corgidrp.data.Dataset): frames
        thresh (float): a threshold
            that continues here. Default: 1.0
        name: no type given

    Returns:
        corgidrp.data.Dataset: the result
    """
    args, summary, returns = parse_google_args(doc)
    assert summary.startswith("Do a thing.")
    assert args["thresh"] == ("float", "a threshold that continues here. Default: 1.0")
    assert args["name"] == ("", "no type given")
    assert returns.startswith("corgidrp.data.Dataset")
