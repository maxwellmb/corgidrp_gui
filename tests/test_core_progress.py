from corgidrp_gui.core.progress import ProgressParser

OK_RUN = """corgidrp_gui recipe: name=l1_to_l2a_basic steps=6 inputs=14 outputdir=/out
Executing recipe: l1_to_l2a_basic
number of frames:  14
Walker step 1/6: prescan_biassub
Walker step 2/6: discard_setup_frames
some random print from a step
/x/y.py:12: UserWarning: something odd
Walker step 3/6: detect_cosmic_rays
corgidrp_gui output: /out/a_l2a.fits
corgidrp_gui output: /out/b_l2a.fits
corgidrp_gui finished: status=ok elapsed=12.3 outputs=2
"""

FAILED_RUN = """Executing recipe: l2a_to_l2b
number of frames:  1
Walker step 1/15: frame_select
Walker step 2/15: convert_to_electrons
Traceback (most recent call last):
  File "walker.py", line 541, in _fill_in_calib_files
    best_cal_file = this_caldb.get_calib(ref_frame, calib_dtype)
ValueError: No valid FlatField calibration in caldb located at /x.csv
corgidrp_gui finished: status=error elapsed=3.0 error=ValueError
"""


def test_ok_run():
    t = [0.0]
    p = ProgressParser(clock=lambda: t.__setitem__(0, t[0] + 1.0) or t[0])
    kinds = [e.kind for e in p.feed_text(OK_RUN)]
    assert kinds.count("step") == 3 and "warning" in kinds and kinds.count("output") == 2
    assert p.recipe_name == "l1_to_l2a_basic" and p.n_frames == 14 and p.total_steps == 6
    assert [s.name for s in p.steps] == ["prescan_biassub", "discard_setup_frames", "detect_cosmic_rays"]
    assert p.steps[0].elapsed == 1.0 and p.steps[1].ended is not None
    assert p.outputs == ["/out/a_l2a.fits", "/out/b_l2a.fits"]
    assert p.finished is True and not p.errors
    assert p.fraction_done == 0.5


def test_failed_run():
    p = ProgressParser()
    events = p.feed_text(FAILED_RUN)
    err = [e for e in events if e.kind == "error"]
    assert len(err) == 1 and err[0].data["type"] == "ValueError" and err[0].data["step"] == "convert_to_electrons"
    assert p.finished is False
    assert p.failing_step().name == "convert_to_electrons"
    assert "Traceback" in p.traceback_text() and "ValueError" in p.traceback_text()
