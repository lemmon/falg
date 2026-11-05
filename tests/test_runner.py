"""Runner tests with fal mocked out: outputs, sidecars, concurrency, interruption. No network."""

import ast
import http.client
import io
import urllib.error
import json
import os
import signal
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from falg import fal, runner
from falg.plan import plan

# keep a developer's ~/.config/falg (key, models.json overrides) out of the tests
_home = tempfile.TemporaryDirectory()
_home_patch = mock.patch.object(fal, "CONFIG_DIR", Path(_home.name))


def setUpModule():
    _home_patch.start()


def tearDownModule():
    _home_patch.stop()
    _home.cleanup()


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (64).to_bytes(4, "big") + (32).to_bytes(4, "big") + b"\0" * 8


def fake_result(delay=0.0, started=None):
    def run(endpoint, args, key, **kw):
        if started is not None:
            started.append(endpoint)
        time.sleep(delay)
        n = args.get("num_images", 1)
        return "req-1", {"seed": 42, "images": [{"url": f"https://x/{i}.png", "content_type": "image/png"}
                                                for i in range(n)]}
    return run


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        patches = [mock.patch.object(fal, "download", lambda url, path: path.write_bytes(PNG))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_files_sidecars_and_gallery(self):
        jobs, meta = plan({"prompts": {"a": "x"}, "models": ["nano-banana-2.1"], "n": 2}, self.out)
        with mock.patch.object(fal, "run", fake_result()):
            failures = runner.execute(jobs, "key", self.out, meta, workers=2)
        self.assertEqual(failures, 0)
        names = sorted(p.name for p in self.out.glob("*.png"))
        self.assertEqual(names, ["a__nano-banana-2.1__01.png", "a__nano-banana-2.1__02.png"])
        side = json.loads((self.out / "a__nano-banana-2.1__01.json").read_text())
        self.assertEqual((side["seed"], side["request_id"], side["width"], side["height"]), (42, "req-1", 64, 32))
        self.assertEqual(side["prompt"], "x")
        self.assertTrue((self.out / "index.html").is_file())
        self.assertEqual(len(json.loads((self.out / "run.json").read_text())["jobs"]), 1)

    def test_many_concurrent_jobs_snapshot_safely(self):
        jobs, meta = plan({"prompts": [f"p{i}" for i in range(60)], "models": ["flux-3"]}, self.out)
        with mock.patch.object(fal, "run", fake_result()):
            failures = runner.execute(jobs, "key", self.out, meta, workers=16)
        self.assertEqual(failures, 0)
        self.assertEqual(len(list(self.out.glob("*.png"))), 60)

    def test_failures_are_recorded_not_fatal(self):
        jobs, meta = plan({"prompts": ["a", "b"], "models": ["flux-3"]}, self.out)

        def flaky(endpoint, args, key, **kw):
            if args["prompt"] == "b":
                raise fal.FalError("boom")
            return fake_result()(endpoint, args, key)
        with mock.patch.object(fal, "run", flaky):
            failures = runner.execute(jobs, "key", self.out, meta)
        self.assertEqual(failures, 1)
        recorded = json.loads((self.out / "run.json").read_text())["jobs"]
        self.assertEqual(sorted(j.get("error", "") for j in recorded), ["", "boom"])

    @unittest.skipUnless(hasattr(signal, "SIGINT") and os.name == "posix", "needs POSIX signals")
    def test_interrupt_cancels_pending_jobs(self):
        jobs, meta = plan({"prompts": [f"q{i}" for i in range(5)], "models": ["flux-3"]}, self.out)
        started = []
        threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        with mock.patch.object(fal, "run", fake_result(delay=1.0, started=started)):
            with self.assertRaises(KeyboardInterrupt):
                runner.execute(jobs, "key", self.out, meta, workers=1)
            time.sleep(1.2)  # let the one running job finish
        self.assertEqual(len(started), 1)
        recorded = json.loads((self.out / "run.json").read_text())["jobs"]
        self.assertEqual(sum(j.get("error", "").startswith("cancelled") for j in recorded), 4)
        finished = [j for j in recorded if j.get("files")]  # the in-flight job was drained and recorded
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0]["request_id"], "req-1")

    def test_an_error_in_the_main_loop_stops_queued_jobs(self):
        jobs, meta = plan({"prompts": [f"q{i}" for i in range(6)], "models": ["flux-3"]}, self.out)
        started, saves, write_text = [], [], Path.write_text

        def failing_write(path, *a, **kw):  # run.json can't be written after the first result
            if path.name == ".run.json.tmp":
                saves.append(1)
                if len(saves) > 1:
                    raise OSError("disk full")
            return write_text(path, *a, **kw)
        events = []
        run = fake_result(delay=0.1, started=started)

        def recording(endpoint, args, key, **kw):
            events.append(kw["no_submit"])
            return run(endpoint, args, key)
        with mock.patch.object(fal, "run", recording), \
                mock.patch.object(Path, "write_text", failing_write):
            with self.assertRaises(OSError):
                runner.execute(jobs, "key", self.out, meta, workers=1)
            time.sleep(0.8)  # still mocked: a leftover worker would run all 6 jobs by now
        self.assertLessEqual(len(started), 2)
        self.assertTrue(events[0].is_set())  # running workers are told to send nothing more

    def test_request_id_is_persisted_at_submission(self):
        jobs, meta = plan({"prompt": "x", "models": ["flux-3"]}, self.out)
        seen = {}

        def slow(endpoint, args, key, on_submit=None, **kw):
            on_submit({"request_id": "req-9", "status_url": "s", "response_url": "r"})
            seen["run.json"] = json.loads((self.out / "run.json").read_text())  # while still running
            return fake_result()(endpoint, args, key)
        with mock.patch.object(fal, "run", slow):
            runner.execute(jobs, "key", self.out, meta)
        self.assertEqual(seen["run.json"]["jobs"][0]["request_id"], "req-9")
        self.assertEqual(seen["run.json"]["jobs"][0]["response_url"], "r")

    @unittest.skipUnless(hasattr(signal, "SIGINT") and os.name == "posix", "needs POSIX signals")
    def test_second_interrupt_stops_polling_promptly(self):
        jobs, meta = plan({"prompts": ["a", "b"], "models": ["flux-3"]}, self.out)

        def http(url, key=None, payload=None, **kw):  # submissions succeed; jobs never finish
            if payload is not None:
                return {"request_id": "req-" + payload["prompt"], "status_url": "s", "response_url": "r"}
            return {"status": "IN_PROGRESS"}
        before = threading.active_count()
        for t in (0.3, 0.6):
            threading.Timer(t, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
        t0 = time.time()
        with mock.patch.object(fal, "http_json", http), self.assertRaises(KeyboardInterrupt):
            runner.execute(jobs, "key", self.out, meta, workers=2)
        deadline = time.time() + 3  # workers wake from their poll wait and exit
        while threading.active_count() > before and time.time() < deadline:
            time.sleep(0.05)
        self.assertLessEqual(threading.active_count(), before)
        self.assertLess(time.time() - t0, 3)
        recorded = json.loads((self.out / "run.json").read_text())["jobs"]
        self.assertEqual(sorted(j["request_id"] for j in recorded), ["req-a", "req-b"])
        self.assertTrue(all(j["error"].startswith("abandoned") for j in recorded))

    def test_download_failure_keeps_request_metadata(self):
        jobs, meta = plan({"prompt": "x", "models": ["flux-3"]}, self.out)

        def broken_download(url, path):
            raise OSError("network down")
        with mock.patch.object(fal, "run", fake_result()), mock.patch.object(fal, "download", broken_download):
            failures = runner.execute(jobs, "key", self.out, meta)
        self.assertEqual(failures, 1)
        job = json.loads((self.out / "run.json").read_text())["jobs"][0]
        self.assertEqual(job["request_id"], "req-1")
        self.assertEqual(job["output_urls"], ["https://x/0.png"])
        self.assertIn("network down", job["error"])

    def test_extra_files_in_a_result_never_take_another_jobs_names(self):
        jobs, meta = plan({"prompt": "x", "models": ["flux-3"], "n": 2}, self.out)  # 2 requests

        def two_files(endpoint, args, key, **kw):  # e.g. an image plus a mask
            return "req-3", {"images": [{"url": "https://x/a.png", "content_type": "image/png"}],
                             "mask": {"url": "https://x/m.png", "content_type": "image/png"}}
        with mock.patch.object(fal, "run", two_files):
            failures = runner.execute(jobs, "key", self.out, meta, workers=2)
        self.assertEqual(failures, 0)
        recorded = [f["file"] for j in json.loads((self.out / "run.json").read_text())["jobs"]
                    for f in j["files"]]
        self.assertEqual(len(recorded), 4)
        self.assertEqual(len(set(recorded)), 4)
        self.assertEqual(sorted(recorded), sorted(p.name for p in self.out.glob("*.png")))
        self.assertIn("image__flux-3__01.png", recorded)
        self.assertIn("image__flux-3__01-2.png", recorded)

    def test_data_uri_sources_are_elided_in_sidecars(self):
        jobs, meta = plan({"prompt": "x", "models": ["flux-3"],
                           "images": ["data:image/png;base64," + "A" * 5000]}, self.out)
        with mock.patch.object(fal, "run", fake_result()):
            runner.execute(jobs, "key", self.out, meta)
        side = json.loads(next(self.out.glob("image__*.json")).read_text())
        self.assertLess(len(side["sources"][0]), 100)

    def test_json_payload_gets_its_own_sidecar(self):
        jobs, meta = plan({"prompt": "x", "models": ["flux-3"]}, self.out)

        def json_result(endpoint, args, key, **kw):
            return "req-2", {"data": {"url": "https://x/data.json", "file_name": "data.json",
                                      "content_type": "application/json"}}
        with mock.patch.object(fal, "run", json_result), \
                mock.patch.object(fal, "download", lambda url, path: path.write_text('{"payload": 1}')):
            runner.execute(jobs, "key", self.out, meta)
        self.assertEqual(json.loads((self.out / "image__flux-3__01.json").read_text()), {"payload": 1})
        side = json.loads((self.out / "image__flux-3__01.sidecar.json").read_text())
        self.assertEqual(side["request_id"], "req-2")


class TestImageSize(unittest.TestCase):
    def test_truncated_headers_give_none(self):
        with tempfile.TemporaryDirectory() as d:
            for name, data in (("a.jpg", b"\xff\xd8\xff\xe0"), ("b.png", PNG[:10]), ("c.png", PNG)):
                (Path(d) / name).write_bytes(data)
            self.assertIsNone(fal.image_size(Path(d) / "a.jpg"))
            self.assertIsNone(fal.image_size(Path(d) / "b.png"))
            self.assertEqual(fal.image_size(Path(d) / "c.png"), (64, 32))


class TestConfirm(unittest.TestCase):
    def test_prompt_goes_to_stderr_keeping_stdout_clean(self):
        import io
        from falg import cli
        out, err = io.StringIO(), io.StringIO()
        stdin = io.StringIO("y\n")
        stdin.isatty = lambda: True
        with mock.patch("sys.stdin", stdin), mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            self.assertTrue(cli.confirm(1.0, False, None))
        self.assertEqual(out.getvalue(), "")
        self.assertIn("Proceed?", err.getvalue())


class TestFalHelpers(unittest.TestCase):
    def test_media_in_finds_nested_files(self):
        result = {"images": [{"url": "https://a/1.png", "content_type": "image/png"}],
                  "extra": {"video": {"url": "https://a/v.mp4", "file_name": "v.mp4"}},
                  "link": {"url": "https://not-a-file"}}
        self.assertEqual([f["url"] for f in fal.media_in(result)], ["https://a/1.png", "https://a/v.mp4"])

    def test_elide_data(self):
        self.assertEqual(fal.elide_data({"a": ["data:image/png;base64,AAAA"]}),
                         {"a": ["data:image/png;base64,...(26 chars)"]})

    def test_key_lookup_order(self):
        # run from an empty dir, so a real ./.env key is never read (or shown in a failure)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {}, clear=True):
            os.chdir(empty)
            (Path(d) / ".env").write_text("export FAL_KEY='from-file'\n")
            self.assertTrue(fal.find_key_source([Path(d)])[0] == "from-file", "expected the .env key")
            with mock.patch.dict(os.environ, {"FAL_KEY": "from-env"}):
                self.assertTrue(fal.find_key() == "from-env", "expected the env var key")


class FakeResponse:
    def __init__(self, body: bytes = b"", error: Exception | None = None):
        self.body, self.error = body, error

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        if self.error:
            raise self.error
        return self.body


class TestNetworkRetries(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(fal.time, "sleep")
        p.start()
        self.addCleanup(p.stop)

    def urlopen(self, *responses):
        calls = []

        def fake(req, timeout=None):
            calls.append(req.get_method())
            r = responses[len(calls) - 1]
            if isinstance(r, Exception):
                raise r
            return r
        return calls, mock.patch("urllib.request.urlopen", fake)

    def test_get_retries_errors_raised_while_reading(self):
        for err in (ConnectionResetError("reset"), http.client.RemoteDisconnected("gone"),
                    http.client.IncompleteRead(b"")):
            with self.subTest(err=type(err).__name__):
                calls, patch = self.urlopen(FakeResponse(error=err), FakeResponse(b'{"status": "OK"}'))
                with patch:
                    self.assertEqual(fal.http_json("https://q/status"), {"status": "OK"})
                self.assertEqual(calls, ["GET", "GET"])

    def test_rate_limited_submission_is_retried(self):
        def http_error(code):
            return urllib.error.HTTPError("https://q", code, "x", {}, io.BytesIO(b""))
        calls, patch = self.urlopen(http_error(429), FakeResponse(b'{"request_id": "r"}'))
        with patch:
            self.assertEqual(fal.http_json("https://q/submit", payload={"prompt": "x"}), {"request_id": "r"})
        self.assertEqual(calls, ["POST", "POST"])
        calls, patch = self.urlopen(http_error(500))  # may have been accepted: never resubmit
        with patch, self.assertRaises(fal.FalError):
            fal.http_json("https://q/submit", payload={"prompt": "x"})
        self.assertEqual(calls, ["POST"])

    def test_submission_waiting_to_retry_is_never_sent_after_interrupt(self):
        stop = threading.Event()
        sleeps = []
        busy = urllib.error.HTTPError("https://q", 429, "x", {"Retry-After": "30"}, io.BytesIO(b""))
        calls, patch = self.urlopen(busy, FakeResponse(b'{"request_id": "r"}'))

        class Waits:  # stands in for the event's wait: Ctrl+C arrives during the back-off
            def is_set(self):
                return stop.is_set()

            def wait(self, seconds):
                sleeps.append(seconds)
                stop.set()
                return True
        with patch, self.assertRaises(fal.Cancelled):
            fal.http_json("https://q/submit", payload={"prompt": "x"}, abort=Waits())
        self.assertEqual((calls, sleeps), (["POST"], [30.0]))

    def test_post_is_not_retried_but_fails_cleanly(self):
        calls, patch = self.urlopen(FakeResponse(error=ConnectionResetError("reset")))
        with patch, self.assertRaises(fal.FalError):
            fal.http_json("https://q/submit", payload={"prompt": "x"})
        self.assertEqual(calls, ["POST"])

    def test_download_retries(self):
        with tempfile.TemporaryDirectory() as d:
            calls, patch = self.urlopen(ConnectionResetError("reset"), FakeResponse(b"img"))
            with patch:
                fal.download("https://x/a.png", Path(d) / "a.png")
            self.assertEqual((Path(d) / "a.png").read_bytes(), b"img")
            self.assertEqual(len(calls), 2)


class TestCall(unittest.TestCase):
    def test_request_id_is_saved_before_the_job_finishes(self):
        from falg import cli

        def interrupted(endpoint, args, key, on_submit=None, **kw):
            on_submit({"request_id": "req-7", "status_url": "s", "response_url": "r"})
            raise KeyboardInterrupt
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fal, "find_key", lambda dirs=(): "key"), \
                mock.patch.object(fal, "run", interrupted), mock.patch("sys.stderr"):
            self.assertEqual(cli.main(["call", "v/ep", "prompt=hi", "-o", d]), 130)
            (saved,) = Path(d).glob("*/result.json")
            record = json.loads(saved.read_text())
            self.assertEqual((record["request_id"], record["response_url"]), ("req-7", "r"))


class TestCli(unittest.TestCase):
    def main(self, *argv):
        from falg import cli
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_interrupt_before_sending_does_not_mention_running_requests(self):
        tty = io.StringIO()
        tty.isatty = lambda: True
        with mock.patch("getpass.getpass", side_effect=KeyboardInterrupt), mock.patch("sys.stdin", tty):
            code, _, err = self.main("auth")  # Ctrl+C at the hidden key prompt
        self.assertEqual(code, 130)
        self.assertNotIn("keep running", err)

    def test_second_interrupt_exits_without_waiting_for_workers(self):
        def stop_waiting(*a, **kw):  # what the runner does on a second Ctrl+C
            runner.abandoned.set()
            raise KeyboardInterrupt
        from falg import cli
        with tempfile.TemporaryDirectory() as d, mock.patch.object(cli, "execute", stop_waiting), \
                mock.patch.object(fal, "find_key", lambda dirs=(): "key"), \
                mock.patch.object(cli.os, "_exit", side_effect=SystemExit) as exit_:
            with self.assertRaises(SystemExit):
                self.main("gen", "x", "-m", "flux-3", "-y", "-o", d)
        exit_.assert_called_once_with(130)

    def test_submission_count_is_per_command(self):
        fal._submitted = 3  # left over from an earlier command in the same process
        tty = io.StringIO()
        tty.isatty = lambda: True
        with mock.patch("getpass.getpass", side_effect=KeyboardInterrupt), mock.patch("sys.stdin", tty):
            _, _, err = self.main("auth")
        self.assertNotIn("keep running", err)

    def test_dry_run_json_is_json(self):
        code, out, _ = self.main("gen", "a fox", "-m", "flux-3", "-n", "2", "--dry-run", "--json")
        body = json.loads(out)
        self.assertEqual((code, body["requests"], body["prompts"][0]["prompt"]), (0, 2, "a fox"))
        from falg.plan import load_registry
        spec = load_registry()["flux-3"]["generate"]
        self.assertAlmostEqual(body["estimated_cost"], 2 * spec["price"])
        self.assertEqual(body["example_request"]["endpoint"], spec["endpoint"])

    def test_max_cost_refuses_models_without_a_price(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fal, "find_key", lambda dirs=(): "key"), \
                mock.patch.object(fal, "run", side_effect=AssertionError("must not send")):
            cfg = Path(d) / "job.json"
            cfg.write_text(json.dumps({"prompt": "x", "models": ["m"], "n": 50,
                                       "model_defs": {"m": {"generate": {"endpoint": "v/m"}}}}))
            code, _, err = self.main("run", str(cfg), "--max-cost", "1", "-o", d)
        self.assertEqual(code, 1)
        self.assertIn("No price for m", err)

    def test_set_overrides_or_fails_loudly(self):
        from falg.cli import apply_set
        cfg = {"prompt": "old"}
        apply_set(cfg, ["prompt=NEW"])
        self.assertEqual(cfg["prompt"], "NEW")
        cfg = {"template": "{subject} {bg}", "vars": {"subject": {"fox": "A fox"}, "bg": "white"}}
        apply_set(cfg, ["bg=black"])
        self.assertEqual(cfg["vars"]["bg"], "black")
        for bad in ("backgrund=x", "bg", "subject=x"):  # typo, no '=', an axis
            with self.subTest(bad=bad), self.assertRaises(SystemExit):
                apply_set(json.loads(json.dumps(cfg)), [bad])
        with self.assertRaises(SystemExit):  # several prompts: use --only
            apply_set({"prompts": ["a", "b"]}, ["prompt=x"])

    def test_set_prompt_needs_a_prompt_in_the_template(self):
        from falg.cli import apply_set
        cfg = json.loads((Path(__file__).parent.parent / "examples" / "chest-logos.json").read_text())
        with self.assertRaises(SystemExit):  # template has no {prompt}: would be ignored
            apply_set(cfg, ["prompt=a cat"])
        with self.assertRaises(SystemExit):  # a prompt axis under vars
            apply_set({"template": "{prompt}", "vars": {"prompt": {"a": "x", "b": "y"}}}, ["prompt=z"])
        cfg = {"template": "{prompt}, {bg}", "prompt": "old", "vars": {"bg": "white"}}
        apply_set(cfg, ["prompts=new"])
        self.assertEqual(cfg["prompt"], "new")

    def test_set_accepts_non_ascii_variable_names(self):
        from falg.cli import apply_set
        cfg = {"template": "{prompt} {pozadí}", "prompt": "x", "vars": {"pozadí": "bílé"}}
        apply_set(cfg, ["pozadí=černé"])
        self.assertEqual(cfg["vars"]["pozadí"], "černé")

    def test_unresolved_variable_stops_a_paid_run(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(fal, "find_key", lambda dirs=(): "key"), \
                mock.patch.object(fal, "run", side_effect=AssertionError("must not send")):
            cfg = Path(d) / "job.json"
            cfg.write_text(json.dumps({"template": "{subjcet} on white", "models": ["flux-3"],
                                       "vars": {"subject": "a fox"}}))
            code, _, err = self.main("run", str(cfg), "-y", "-o", d)
            self.assertEqual(code, 1)
            self.assertIn("{subjcet}", err)
            code, _, _ = self.main("run", str(cfg), "--dry-run")  # still previewable
            self.assertEqual(code, 0)
        code, _, _ = self.main("gen", "a sign that says {hello}", "-m", "flux-3", "--dry-run")
        self.assertEqual(code, 0)  # a plain prompt may contain braces

    def test_call_args_must_be_an_object(self):
        with tempfile.TemporaryDirectory() as d:
            body = Path(d) / "body.json"
            body.write_text("[1]")
            code, _, err = self.main("call", "v/ep", "--args", str(body), "--dry-run")
        self.assertEqual((code, err.startswith("error: ")), (1, True))

    def test_workers_must_be_positive(self):
        with self.assertRaises(SystemExit):
            self.main("gen", "x", "--workers", "0", "--dry-run")

    def test_set_beats_an_axis_options_own_set(self):
        from falg.cli import apply_set
        from falg.plan import combos
        cfg = json.loads((Path(__file__).parent.parent / "examples" / "chest-logos.json").read_text())
        apply_set(cfg, ["colour=BLUE"])
        prompts = [c["prompt"] for c in combos(cfg)]
        self.assertTrue(prompts and all("BLUE" in p and "neon pink colour" not in p for p in prompts))

    def test_no_arguments_prints_help(self):
        code, out, _ = self.main()
        self.assertEqual(code, 0)
        self.assertIn("Commands:", out)

    def test_partial_failure_exits_nonzero(self):
        def half(endpoint, args, key, **kw):
            if args["prompt"] == "b":
                raise fal.FalError("boom")
            return fake_result()(endpoint, args, key)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(fal, "run", half), \
                mock.patch.object(fal, "find_key", lambda dirs=(): "key"), \
                mock.patch.object(fal, "download", lambda url, path: path.write_bytes(PNG)):
            cfg = Path(d) / "job.json"
            cfg.write_text(json.dumps({"prompts": ["a", "b"], "models": ["flux-3"]}))
            code, out, _ = self.main("run", str(cfg), "-y", "--json", "-o", d)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["failed"], 1)

    def test_unsafe_gallery_background_is_rejected_before_spending(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "job.json"
            cfg.write_text(json.dumps({"prompt": "x", "models": ["flux-3"],
                                       "gallery_background": "#888}</style><script>alert(1)</script>"}))
            code, _, err = self.main("run", str(cfg), "--dry-run")
            self.assertEqual(code, 1)
            self.assertIn("gallery_background", err)
            jobs, meta = plan({"prompt": "x", "models": ["flux-3"]}, Path(d))
            runner.write_gallery(Path(d), jobs, {**meta, "gallery_background": "red;}</style><script>"})
            self.assertNotIn("<script>", (Path(d) / "index.html").read_text())
        for ok in ("#888", "white", "rgb(10 20 30 / 50%)", "oklch(70% 0.1 200deg)"):
            self.assertEqual(runner.check_background(ok), ok)
        for bad in ("url(//example.com/t.gif)", "red; color: blue", "image-set(x)"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                runner.check_background(bad)

    def test_missing_files_give_an_error_line_not_a_traceback(self):
        code, _, err = self.main("run", "does-not-exist.json")
        self.assertEqual((code, err.startswith("error: ")), (1, True))
        code, _, err = self.main("gen", "x", "-i", "does-not-exist.png", "--dry-run")
        self.assertEqual((code, err.startswith("error: ")), (1, True))
        with self.assertRaises(SystemExit):  # --file without '='
            self.main("call", "v/ep", "--file", "image_url", "--dry-run")

    def test_call_arguments_after_options(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / "a.png"
            img.write_bytes(PNG)
            code, out, _ = self.main("call", "v/ep", "--dry-run", "prompt=hi",
                                     "--file", f"image_url={img}", "seed:=7")
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertEqual((body["prompt"], body["seed"]), ("hi", 7))
        self.assertTrue(body["image_url"].startswith("data:image/png"))
        with self.assertRaises(SystemExit):  # other commands still reject stray arguments
            self.main("models", "stray=1")


class TestSource(unittest.TestCase):
    def test_text_files_are_read_and_written_as_utf8(self):
        # without encoding=, Windows (Python < 3.15) uses the locale code page
        src = Path(fal.__file__).parent
        for path in src.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ("read_text", "write_text")):
                    with self.subTest(file=path.name, line=node.lineno):
                        self.assertIn("encoding", [k.arg for k in node.keywords])


if __name__ == "__main__":
    unittest.main()
