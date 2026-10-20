import json

from corgidrp_gui.core.queue import JobQueue
from corgidrp_gui.core.queue_items import QueueRequest
from corgidrp_gui.core.recipes import Recipe, RecipeStep


def _recipe(name, inputs=("a.fits",)):
    return Recipe(name=name, inputs=list(inputs), steps=[RecipeStep("prescan_biassub"), RecipeStep("save")])


def test_chain_scheduling_and_skip(tmp_path):
    q = JobQueue(str(tmp_path))
    events = []
    q.listeners.append(lambda e, j: events.append((e, j.name if j else None)))
    req = QueueRequest(chains=[[_recipe("one"), _recipe("two", ())], [_recipe("solo")]], outputdir=str(tmp_path / "out"))
    jobs = q.add_request(req)
    assert [j.name for j in jobs] == ["one", "two", "solo"]
    assert jobs[1].depends_on == jobs[0].id and jobs[0].chain_length == 2 and jobs[2].chain_length == 1
    assert all(j.recipe_path.endswith(".json") for j in jobs) and json.load(open(jobs[0].recipe_path))["name"] == "one"
    assert jobs[0].recipe.outputdir == str(tmp_path / "out")

    assert q.next_runnable() is jobs[0]           # 'two' waits for 'one'; 'solo' is after it in order
    q.prepare_launch(jobs[0])
    assert q.next_runnable() is None              # one worker
    q.max_workers = 2
    assert q.next_runnable() is jobs[2]           # 'two' still blocked by its dependency
    # 'one' finishes successfully with outputs -> 'two' gets them as inputs
    jobs[0].parser.feed_text("corgidrp_gui output: /x/a_l2a.fits\ncorgidrp_gui finished: status=ok elapsed=1")
    q.mark_finished(jobs[0], 0)
    assert jobs[0].status == "done" and jobs[0].outputs == ["/x/a_l2a.fits"]
    nxt = q.next_runnable()
    assert nxt is jobs[1]
    q.prepare_launch(nxt)
    assert nxt.inputs_from and open(nxt.inputs_from).read().strip() == "/x/a_l2a.fits"
    assert nxt.recipe.inputs == ["/x/a_l2a.fits"]
    # failure path: a failing head skips its dependents
    jobs[1].parser.feed_text("Walker step 1/2: prescan_biassub\nTraceback (most recent call last):\n  x\nValueError: boom\n")
    q.mark_finished(jobs[1], 1)
    assert jobs[1].status == "failed" and "prescan_biassub" in jobs[1].message and "boom" in jobs[1].message
    assert q.counts()["failed"] == 1
    assert ("finished", "two") in events and ("started", "one") in events


def test_skip_requeue_persist(tmp_path):
    q = JobQueue(str(tmp_path))
    jobs = q.add_request(QueueRequest(chains=[[_recipe("h"), _recipe("t", ())]], outputdir=str(tmp_path)))
    q.prepare_launch(jobs[0])
    q.mark_finished(jobs[0], 2)
    assert jobs[0].status == "failed" and jobs[1].status == "skipped"
    q.requeue(jobs[0])
    assert jobs[0].status == "waiting" and jobs[1].status == "waiting"
    assert q.jobs.index(jobs[0]) < q.jobs.index(jobs[1])
    q.paused = True
    assert q.next_runnable() is None
    q.paused = False
    q.prepare_launch(jobs[0])
    q.save()
    q2 = JobQueue(str(tmp_path))
    assert q2.load() == 2
    a, b = q2.jobs
    assert a.status == "aborted" and "closed" in a.message     # was running when saved
    assert b.status == "waiting" and b.depends_on == a.id and b.recipe.name == "t"
    q2.clear_finished()
    assert [j.name for j in q2.jobs] == ["t"]
    q2.remove(q2.jobs[0])
    assert not q2.jobs


def test_step_states_and_progress(tmp_path):
    q = JobQueue(str(tmp_path))
    (job,) = q.add_request(QueueRequest(chains=[[Recipe(name="r", inputs=["a"], steps=[RecipeStep("a1"), RecipeStep("b2", skip=True), RecipeStep("c3"), RecipeStep("save")])]], outputdir=str(tmp_path)))
    assert job.progress_text() == "—"
    q.prepare_launch(job)
    job.parser.feed_text("Walker step 1/4: a1\nWalker step 3/4: c3\n")
    states = job.step_states()
    assert [s[1] for s in states] == ["done", "skipped", "running", "pending"]
    assert job.progress_text() == "3/4"
    job.parser.feed_text("corgidrp_gui finished: status=ok elapsed=2")
    q.mark_finished(job, 0)
    assert [s[1] for s in job.step_states()] == ["done", "skipped", "done", "pending"]
    assert job.progress_text() == "4/4"
