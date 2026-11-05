"""Planner tests: prompt expansion, sizes, cost estimates, validation. No network."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from falg import fal
from falg.plan import build_args, combos, plan, render, size_args

HERE = Path(__file__).parent

# keep a developer's ~/.config/falg/models.json (e.g. price overrides) out of the tests
_home = tempfile.TemporaryDirectory()
_home_patch = mock.patch.object(fal, "CONFIG_DIR", Path(_home.name))


def setUpModule():
    _home_patch.start()


def tearDownModule():
    _home_patch.stop()
    _home.cleanup()


class TestPrompts(unittest.TestCase):
    def test_axes_constants_and_overrides(self):
        cfg = {
            "template": ["{subject}.", "Style: {style} {bg}"],
            "vars": {
                "subject": {"fox": "A fox", "owl": "An owl"},
                "style": {"riso": "Riso.", "ink": {"text": "Ink.", "set": {"bg": "On black."}}},
                "bg": ["On", "white."],
            },
        }
        got = {c["label"]: c["prompt"] for c in combos(cfg)}
        self.assertEqual(got["fox__riso"], "A fox. Style: Riso. On white.")
        self.assertEqual(got["owl__ink"], "An owl. Style: Ink. On black.")
        self.assertEqual(len(got), 4)

    def test_only_filters_and_validates(self):
        cfg = {"vars": {"s": {"a": "A", "b": "B"}}, "template": "{s}"}
        self.assertEqual([c["label"] for c in combos(cfg, {"s": {"b"}})], ["b"])
        with self.assertRaises(ValueError):
            combos(cfg, {"s": {"zzz"}})
        with self.assertRaises(ValueError):
            combos(cfg, {"nope": {"a"}})

    def test_nested_and_unresolved_variables(self):
        self.assertEqual(render("{a}", {"a": "x {b}", "b": "y"}), "x y")
        c = combos({"template": "{a} {missing}", "vars": {"a": "x"}})[0]
        self.assertEqual(c["unresolved"], ["missing"])
        c = combos({"template": "{a}", "vars": {"a": "{b}", "b": "{a}"}})[0]  # a cycle
        self.assertTrue(c["unresolved"])

    def test_label_collision_is_rejected(self):
        cfg = {"vars": {"s": {"A B": "1", "a-b": "2"}}, "template": "{s}"}
        with self.assertRaises(ValueError):
            combos(cfg)

    def test_long_labels_are_shortened_but_stay_unique(self):
        long = "x" * 48
        axes = {f"a{i}": {long: "t", long[:-1] + "y": "u"} for i in range(6)}
        cs = combos({"vars": axes, "template": "{a0}"})
        labels = [c["label"] for c in cs]
        self.assertEqual(len(set(labels)), len(labels))
        name = f"{labels[0]}__{'m' * 64}__9999.sidecar.json"
        self.assertLess(len(name.encode()), 255)

    def test_prompts_string_is_rejected_not_split_into_characters(self):
        with self.assertRaises(ValueError):
            combos({"prompts": "a red fox"})

    def test_prompts_list_shortcut(self):
        self.assertEqual([c["label"] for c in combos({"prompts": ["x", "y"]})], ["p01", "p02"])


class TestSizesAndArgs(unittest.TestCase):
    def test_px_sizes_are_multiples_of_16_within_budget(self):
        spec = {"size": "px", "pixels": 2048 * 2048}
        self.assertEqual(size_args(spec, "1:1"), {"image_size": {"width": 2048, "height": 2048}})
        self.assertEqual(size_args(spec, "3:2"), {"image_size": {"width": 2496, "height": 1664}})
        wh = size_args({"size": "px", "pixels": 4596736}, "16:9")["image_size"]
        self.assertTrue(wh["width"] % 16 == 0 and wh["height"] % 16 == 0)
        self.assertLessEqual(wh["width"] * wh["height"], 4596736)

    def test_enum_and_aspect_modes(self):
        self.assertEqual(size_args({"size": "aspect"}, "3:2"), {"aspect_ratio": "3:2"})
        with self.assertRaises(ValueError):
            size_args({"size": "enum", "enum_map": {"1:1": "square_hd"}}, "5:4")

    def test_params_override_last(self):
        args = build_args({"size": "aspect", "params": {"resolution": "2K"}, "batch": True},
                          "p", 2, "1:1", [], {"resolution": "4K"})
        self.assertEqual(args, {"prompt": "p", "aspect_ratio": "1:1", "resolution": "4K", "num_images": 2})


class TestPlan(unittest.TestCase):
    def test_batch_vs_single_requests(self):
        jobs, meta = plan({"prompt": "x", "models": ["nano-banana-2.1", "flux-3"], "n": 3}, HERE)
        by_model = {}
        for j in jobs:
            by_model.setdefault(j["model"], []).append((j["index"], j["count"]))
        self.assertEqual(by_model["nano-banana-2.1"], [(1, 3)])          # one request, num_images=3
        self.assertEqual(by_model["flux-3"], [(1, 1), (2, 1), (3, 1)])   # three requests
        self.assertEqual(meta["mode"], "generate")

    def test_batches_are_split_at_the_endpoint_limit(self):
        jobs, _ = plan({"prompt": "x", "models": ["nano-banana-2.1"], "n": 9}, HERE)  # max_batch 4
        self.assertEqual([(j["index"], j["count"]) for j in jobs], [(1, 4), (5, 4), (9, 1)])
        self.assertEqual([j["args"].get("num_images") for j in jobs], [4, 4, None])
        self.assertAlmostEqual(sum(j["price"] for j in jobs), 9 * 0.059)
        defs = {"m": {"generate": {"endpoint": "v/m", "price": 0.01, "batch": True}}}
        jobs, _ = plan({"prompt": "x", "models": ["m"], "n": 5, "model_defs": defs}, HERE)
        self.assertEqual([j["count"] for j in jobs], [4, 1])  # assumed cap without max_batch

    def test_builtin_batch_models_declare_their_limit(self):
        from falg.plan import load_registry
        for name, spec in load_registry().items():
            for mode, s in spec.items():
                if isinstance(s, dict) and s.get("batch"):
                    with self.subTest(model=name, mode=mode):
                        self.assertIsInstance(s.get("max_batch"), int)

    def test_estimate_follows_num_images_override(self):
        jobs, _ = plan({"prompt": "x", "models": ["nano-banana-2.1"],
                        "params": {"*": {"num_images": 4}}}, HERE)
        self.assertEqual(jobs[0]["count"], 4)
        self.assertAlmostEqual(jobs[0]["price"], 4 * 0.059)

    def test_fixed_seed_differs_per_request_when_n_is_split(self):
        jobs, _ = plan({"prompt": "x", "models": ["flux-3"], "n": 3, "params": {"*": {"seed": 7}}}, HERE)
        self.assertEqual([j["args"]["seed"] for j in jobs], [7, 8, 9])
        jobs, _ = plan({"prompt": "x", "models": ["nano-banana-2.1"], "n": 8,
                        "params": {"*": {"seed": 7}}}, HERE)  # two requests of 4
        self.assertEqual([j["args"]["seed"] for j in jobs], [7, 11])
        jobs, _ = plan({"prompt": "x", "models": ["nano-banana-2.1"], "n": 3,
                        "params": {"*": {"seed": 7}}}, HERE)  # one request: seed as given
        self.assertEqual([j["args"]["seed"] for j in jobs], [7])

    def test_seed_given_as_text_is_offset_too(self):  # -p seed=7 sends the string "7"
        jobs, _ = plan({"prompt": "x", "models": ["flux-3"], "n": 3, "params": {"*": {"seed": "7"}}}, HERE)
        self.assertEqual([j["args"]["seed"] for j in jobs], [7, 8, 9])

    def test_null_in_config_params_removes_the_key(self):
        jobs, _ = plan({"prompt": "x", "models": ["flux-3"],
                        "params": {"flux-3": {"output_format": None}}}, HERE)
        self.assertNotIn("output_format", jobs[0]["args"])

    def test_model_without_price_is_unknown_not_free(self):
        defs = {"m": {"generate": {"endpoint": "v/m"}}}
        jobs, _ = plan({"prompt": "x", "models": ["m"], "model_defs": defs}, HERE)
        self.assertIsNone(jobs[0]["price"])

    def test_model_defs_params_merge_with_builtins(self):
        defs = {"flux-3": {"generate": {"params": {"seed": 7, "output_format": None}}}}
        jobs, _ = plan({"prompt": "x", "models": ["flux-3"], "model_defs": defs}, HERE)
        args = jobs[0]["args"]
        self.assertEqual((args["seed"], args["resolution"]), (7, "2k"))
        self.assertNotIn("output_format", args)  # null removes a built-in param

    def test_px_edit_with_auto_aspect_follows_the_source(self):
        png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + (300).to_bytes(4, "big")
               + (200).to_bytes(4, "big") + b"\0" * 8)  # just the header falg reads
        defs = {"m": {"edit": {"endpoint": "v/m", "price": 0.01, "size": "px", "pixels": 1048576}}}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "photo.png").write_bytes(png)
            jobs, _ = plan({"prompt": "x", "models": ["m"], "model_defs": defs,
                            "images": ["photo.png"]}, Path(d))
            size = jobs[0]["args"]["image_size"]
            self.assertAlmostEqual(size["width"] / size["height"], 1.5, delta=0.05)
            jobs, _ = plan({"prompt": "x", "models": ["m"], "model_defs": defs,
                            "images": ["https://x/a.png"]}, Path(d))
            self.assertNotIn("image_size", jobs[0]["args"])  # unknown: the endpoint decides

    def test_models_string_is_rejected_not_split_into_characters(self):
        with self.assertRaisesRegex(ValueError, "models must be a list"):
            plan({"prompt": "x", "models": "flux-3"}, HERE)

    def test_underscore_notes_are_never_prompts_or_options(self):
        cfg = {"template": "{prompt} {style}",
               "prompts": {"_note": "try owls", "fox": "a fox"},
               "vars": {"style": {"_todo": "chalk?", "riso": "Riso."}, "_axis": {"a": "x", "b": "y"}},
               "params": {"_why": {"seed": 1}, "_version": 2, "*": {"_note": "keep png", "seed": 3}}}
        jobs, _ = plan({**cfg, "models": ["flux-3"]}, HERE)
        self.assertEqual([j["prompt"] for j in jobs], ["a fox Riso."])
        self.assertEqual(jobs[0]["args"]["seed"], 3)
        self.assertNotIn("_note", jobs[0]["args"])  # notes are never sent to fal

    def test_ideogram_sizes_are_from_its_accepted_list(self):
        from falg.plan import load_registry
        spec = load_registry()["ideogram-4.5"]["generate"]
        for aspect in ("1:1", "3:2", "2:3", "4:3", "3:4", "16:9", "9:16"):
            with self.subTest(aspect=aspect):
                size = size_args(spec, aspect)["image_size"]
                w, h = (int(x) for x in aspect.split(":"))
                self.assertAlmostEqual(size["width"] / size["height"], w / h, delta=0.02)
        with self.assertRaises(ValueError):  # not on the list: an error before anything is sent
            size_args(spec, "21:9")

    def test_misspelled_params_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["flux-3"], "params": {"flux3": {"seed": 7}}}, HERE)
        # a registry model not in this run is fine (configs run with -m subsets)
        plan({"prompt": "x", "models": ["flux-3"], "params": {"nano-banana-2.1": {"seed": 7}}}, HERE)

    def test_bad_aspect_is_a_value_error(self):
        for bad in ("1:0", "0:1", "x:2", "-3:2"):
            with self.subTest(aspect=bad), self.assertRaises(ValueError):
                plan({"prompt": "x", "models": ["gpt-image-2.5"]}, HERE, aspect=bad)

    def test_invalid_counts_are_rejected(self):
        for bad in ({"n": 0}, {"n": -1}, {"n": "2"}, {"n": True},
                    {"params": {"*": {"num_images": 0}}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                plan({"prompt": "x", "models": ["nano-banana-2.1"], **bad}, HERE)

    def test_unknown_model_and_missing_mode(self):
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["nope"]}, HERE)
        with self.assertRaises(ValueError):  # recraft-vector has no edit endpoint
            plan({"prompt": "x", "models": ["recraft-vector"], "images": ["https://x/y.png"]}, HERE)

    def test_duplicate_and_unsafe_model_names_are_rejected(self):
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["flux-3", "flux-3"]}, HERE)
        defs = {"vendor/model": {"generate": {"endpoint": "vendor/model", "price": 0.01}}}
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["vendor/model"], "model_defs": defs}, HERE)

    def test_model_names_differing_only_in_case_are_rejected(self):
        defs = {"Flux-3": {"generate": {"endpoint": "v/m", "price": 0.01}}}
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["flux-3", "Flux-3"], "model_defs": defs}, HERE)

    def test_prompt_override_in_params_is_rejected(self):
        for scope in ("*", "flux-3"):
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                plan({"prompt": "x", "models": ["flux-3"], "params": {scope: {"prompt": "other"}}}, HERE)
        defs = {"flux-3": {"generate": {"params": {"prompt": "cat"}}}}  # registry/model_defs too
        with self.assertRaises(ValueError):
            plan({"prompt": "x", "models": ["flux-3"], "model_defs": defs}, HERE)

    def test_images_switch_to_edit_endpoints(self):
        jobs, meta = plan({"prompt": "x", "models": ["nano-banana-2.1"],
                           "images": ["https://example.com/a.png"]}, HERE)
        self.assertEqual(meta["mode"], "edit")
        self.assertEqual(jobs[0]["endpoint"], "google/nano-banana-2.1/edit")
        self.assertEqual(jobs[0]["args"]["image_urls"], ["https://example.com/a.png"])
        self.assertEqual(jobs[0]["args"]["aspect_ratio"], "auto")

    def test_image_paths(self):
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"HOME": home}):
            (Path(home) / "pic.png").write_bytes(b"png")
            jobs, _ = plan({"prompt": "x", "models": ["flux-3"], "images": ["~/pic.png"]}, HERE)
            self.assertEqual(jobs[0]["sources"], [str((Path(home) / "pic.png").resolve())])
            for bad in (["~/missing.png"], "~/pic.png"):  # missing file; a string, not a list
                with self.subTest(images=bad), self.assertRaises(ValueError):
                    plan({"prompt": "x", "models": ["flux-3"], "images": bad}, HERE)

    def test_examples_plan(self):
        for cfg_file in sorted((HERE.parent / "examples").glob("*.json")):
            import json
            cfg = json.loads(cfg_file.read_text())
            if cfg.get("images"):
                continue  # placeholder paths
            with self.subTest(cfg_file.name):
                jobs, _ = plan(cfg, cfg_file.parent)
                self.assertTrue(jobs)
                self.assertFalse(any(j["unresolved"] for j in jobs))


if __name__ == "__main__":
    unittest.main()
