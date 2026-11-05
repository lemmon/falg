"""falg: generate and edit images on fal.ai from JSON job configs or one-liners.

Commands:
  run CONFIG.json     expand a job config (prompt template x variable axes x models) and run it
  gen "PROMPT"        quick one-off generation
  edit SRC "PROMPT"   edit an image (local file or URL) with edit models
  call ENDPOINT k=v   call ANY fal endpoint with raw arguments; downloads every file in the result
  auth [KEY]          save your fal API key globally (~/.config/falg/.env)
  models              list the model registry
  catalog             refresh MODELS.md: dated list of recent fal models + registry check
  search QUERY        search fal's model catalog
  schema ENDPOINT     show an endpoint's input parameters
  cutout IMG...       remove a white/black background -> print-ready PNG (needs falg[cutout])

Every run writes to <out>/<timestamp>-<name>/: the files, one .json sidecar per file (prompt,
model, args, seed, request id, size, cost estimate), run.json and index.html (a comparison grid).
FAL_KEY comes from the environment or a .env in the current dir, the config's dir or ~/.config/falg.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, fal
from .plan import VAR, load_registry, plan, slug
from . import runner
from .runner import check_background, execute, log, make_run_dir


# --------------------------------------------------------------------------- helpers


def parse_kv(items: list[str]) -> dict:
    """key=value (string) or key:=json (number, bool, object...), like `fal api`."""
    out = {}
    for it in items:
        eq = it.find("=")
        if eq <= 0:
            raise SystemExit(f"expected key=value or key:=json, got {it!r}")
        if it[eq - 1] == ":":
            out[it[:eq - 1]] = json.loads(it[eq + 1:])
        else:
            out[it[:eq]] = it[eq + 1:]
    return out


def parse_only(items: list[str] | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for it in items or []:
        k, _, v = it.partition("=")
        if not v:
            raise SystemExit(f"--only expects axis=name[,name], got {it!r}")
        out.setdefault(k, set()).update(x.strip() for x in v.split(",") if x.strip())
    return out


def positive_int(s: str) -> int:
    n = int(s)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {n}")
    return n


def confirm(cost: float, yes: bool, max_cost: float | None, unpriced: list[str] = ()) -> bool:
    if max_cost is not None and unpriced and not yes:
        log(f"No price for {', '.join(unpriced)}, so --max-cost can't be checked; nothing sent. "
            "Add \"price\" to the model (model_defs or ~/.config/falg/models.json), or use -y.")
        return False
    if max_cost is not None and cost > max_cost:
        log(f"Estimated ~${cost:.2f} exceeds --max-cost ${max_cost:.2f}; nothing sent.")
        return False
    if yes or max_cost is not None:  # an explicit budget counts as approval up to that amount
        return True
    if not sys.stdin.isatty():
        log("No terminal for the cost confirmation; re-run with -y (or --max-cost N).")
        return False
    print("Proceed? [y/N] ", end="", file=sys.stderr, flush=True)  # stderr: keep stdout clean for --json
    answer = sys.stdin.readline()
    return answer.strip().lower() in ("y", "yes")


def get_key(*dirs: Path) -> str:
    key = fal.find_key(dirs)
    if not key:
        raise SystemExit("FAL_KEY not found: export it, or put FAL_KEY=... in ~/.config/falg/.env "
                         "(or a .env in the current directory).")
    return key


def summarize(jobs: list[dict], meta: dict) -> tuple[float, list[str]]:
    """Log the plan; return (estimated cost of the priced jobs, models without a price)."""
    cost = sum(j["price"] for j in jobs if j["price"] is not None)
    unpriced = list(dict.fromkeys(j["model"] for j in jobs if j["price"] is None))
    labels = list(dict.fromkeys(j["label"] for j in jobs))
    imgs = sum(j["count"] for j in jobs)
    log(f"[{meta['mode']}] {len(labels)} prompt(s) x {len(meta['models'])} model(s) x {meta['n']} = "
        f"{imgs} image(s), {len(jobs)} request(s), aspect {meta['aspect']}, estimated ~${cost:.2f}"
        + (f" plus unpriced {', '.join(unpriced)}" if unpriced else ""))
    if unpriced:
        log(f"warning: no price for {', '.join(unpriced)}; the estimate leaves them out")
    bad = sorted({v for j in jobs for v in j["unresolved"]})
    if bad:
        log(f"warning: unresolved template variables: {', '.join('{' + b + '}' for b in bad)}")
    return cost, unpriced


def run_jobs(cfg: dict, base_dir: Path, args, *, images: list[str] | None = None,
             config_path: str | None = None) -> int:
    jobs, meta = plan(cfg, base_dir, models=args.models, n=args.n, aspect=args.aspect,
                      only=parse_only(getattr(args, "only", None)), images=images)
    if not jobs:
        raise SystemExit("nothing to run")
    background = check_background(cfg.get("gallery_background", "#888"))
    cost, unpriced = summarize(jobs, meta)
    if args.dry_run:
        prompts = {j["label"]: j["prompt"] for j in jobs}
        example = {"endpoint": jobs[0]["endpoint"], **fal.elide_data(jobs[0]["args"])}
        if args.json:
            print(json.dumps({
                "dry_run": True, **meta, "requests": len(jobs), "images": sum(j["count"] for j in jobs),
                "estimated_cost": round(cost, 4), "unpriced_models": unpriced,
                "unresolved": sorted({v for j in jobs for v in j["unresolved"]}),
                "prompts": [{"label": k, "prompt": v} for k, v in prompts.items()],
                "example_request": example}, indent=2, ensure_ascii=False))
            return 0
        for label, prompt in prompts.items():
            print(f"\n[{label}] ({len(prompt)} chars)\n{prompt}")
        print("\nExample request:", json.dumps(example)[:600])
        return 0
    bad = sorted({v for j in jobs for v in j["unresolved"]})
    if bad and ("vars" in cfg or "template" in cfg):  # a typo; a plain prompt may use braces
        raise ValueError(f"unresolved template variables {', '.join('{' + b + '}' for b in bad)}: "
                         "define them under vars or fix the name (--dry-run shows the prompts)")
    key = get_key(base_dir)
    if not confirm(cost, args.yes, args.max_cost, unpriced):
        return 1
    parent = Path(args.out) if args.out else (base_dir / cfg.get("out", "generations"))
    name = slug(cfg.get("name") or (Path(config_path).stem if config_path else "gen"))
    out_dir = make_run_dir(parent, name)
    full = {"created": datetime.now().isoformat(timespec="seconds"), "falg": __version__,
            "config_path": config_path, "config": fal.elide_data(cfg), **meta,
            "gallery_background": background}
    log(f"-> {out_dir}")
    failures = execute(jobs, key, out_dir, full, workers=args.workers)
    outputs = [f for j in jobs for f in j.get("files", [])]
    files = [str(out_dir / f["file"]) for f in outputs]
    if args.json:
        print(json.dumps({"run_dir": str(out_dir), "files": files,
                          "sidecars": [str(out_dir / f["sidecar"]) for f in outputs],
                          "failed": failures}, indent=2))
    else:
        print(f"Done: {out_dir}/index.html ({len(files)} file(s)"
              + (f", {failures} failed request(s))" if failures else ")"))
    return 1 if failures else 0  # scripts and agents must see partial failures too


# --------------------------------------------------------------------------- commands


def cmd_run(args) -> int:
    path = Path(args.config).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    apply_set(cfg, args.set or [])
    return run_jobs(cfg, path.parent, args, config_path=str(path))


def apply_set(cfg: dict, items: list[str]) -> None:
    """--set var=text overrides a constant variable (or the single prompt). Anything else is an
    error: a typo or an axis would otherwise run, and be paid for, without the override."""
    # names the prompts actually use; without a template, the template is "{prompt}"
    used = set(VAR.findall(json.dumps(cfg, ensure_ascii=False))) | ({"prompt"} if "template" not in cfg else set())
    for kv in items:
        k, eq, v = kv.partition("=")
        if not eq or not k:
            raise SystemExit(f"--set expects VAR=TEXT, got {kv!r}")
        if k == "prompts":
            k = "prompt"
        if k not in used:
            raise SystemExit(f"--set {k}: the prompts don't use {{{k}}} "
                             f"(they use: {', '.join(sorted(used)) or 'nothing'})")
        if k == "prompt":
            if ("prompts" in cfg or isinstance(cfg.get("prompt"), dict)
                    or isinstance(cfg.get("vars", {}).get("prompt"), dict)):
                raise SystemExit("--set prompt: this config has several prompts; "
                                 "pick some with --only prompt=NAME")
            cfg["prompt"] = v  # combos() reads cfg["prompt"] over vars["prompt"]
            continue
        if isinstance(cfg.get("vars", {}).get(k), dict):
            raise SystemExit(f"--set {k}: {k} is an axis; pick options with --only {k}=NAME")
        cfg.setdefault("vars", {})[k] = v
        # an axis option's own "set" would replace the value for its prompts: the command line wins
        axes = [a for a in (*cfg["vars"].values(), cfg.get("prompts"), cfg.get("prompt"))
                if isinstance(a, dict)]
        for axis in axes:
            for opt in axis.values():
                if isinstance(opt, dict) and k in opt.get("set", {}):
                    opt["set"] = {sk: sv for sk, sv in opt["set"].items() if sk != k}


def cmd_gen(args) -> int:
    cfg = {"name": args.name or slug(" ".join(args.prompt.split()[:5])), "prompt": args.prompt,
           "params": {"*": parse_kv(args.param or [])}}
    return run_jobs(cfg, Path.cwd(), args, images=args.image or [])


def cmd_edit(args) -> int:
    args.image = [args.source, *(args.image or [])]
    args.name = args.name or "edit-" + slug(" ".join(args.prompt.split()[:4]))
    return cmd_gen(args)


def cmd_call(args) -> int:
    payload = {}
    if args.args:
        payload = json.loads(sys.stdin.read() if args.args == "-" else Path(args.args).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"--args must hold a JSON object, got a {type(payload).__name__}")
    payload.update(parse_kv(args.kv))
    for k in args.file or []:  # key=path: upload a local file as a data URI
        name, _, p = k.partition("=")
        if not name or not p:
            raise SystemExit(f"--file expects KEY=PATH, got {k!r}")
        payload[name] = fal.as_url(p)
    if args.dry_run:
        print(json.dumps({"endpoint": args.endpoint, **fal.elide_data(payload)}, indent=2))
        return 0
    key = get_key()  # raw calls have no price table, so no cost confirmation
    out_dir = make_run_dir(Path(args.out or "generations"), slug(args.name or args.endpoint))
    t0 = datetime.now()
    log(f"-> {out_dir}")
    record = {"endpoint": args.endpoint, "args": fal.elide_data(payload)}

    def save_record() -> None:
        (out_dir / "result.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                             encoding="utf-8")

    def submitted(info: dict) -> None:  # persist the request id at once: the job is now paid for
        record.update(info)
        save_record()
        log(f"   request {info.get('request_id')} (saved to result.json)")

    rid, result = fal.run(args.endpoint, payload, key, max_wait=args.timeout, on_submit=submitted)
    # write the raw result before downloading: it holds the URLs even if a download fails
    record.update(request_id=rid, result=result)
    save_record()
    files = []
    for i, f in enumerate(fal.media_in(result), 1):
        name = f"{slug(args.endpoint.split('/')[-1])}__{i:02d}{fal.ext_for(f)}"
        fal.download(f["url"], out_dir / name)
        if not (f.get("width") and f.get("height")) and (wh := fal.image_size(out_dir / name)):
            f = {**f, "width": wh[0], "height": wh[1]}
        (out_dir / fal.sidecar_name(name)).write_text(json.dumps({
            "file": name, "created": t0.isoformat(timespec="seconds"), "endpoint": args.endpoint,
            "request_id": rid, "seed": result.get("seed"), "url": f["url"],
            "width": f.get("width"), "height": f.get("height"), "content_type": f.get("content_type"),
            "args": fal.elide_data(payload)}, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(str(out_dir / name))
    print(json.dumps({"run_dir": str(out_dir), "files": files}, indent=2) if args.json
          else f"Done: {out_dir} ({len(files)} file(s))")
    return 0


def cmd_models(args) -> int:
    reg = load_registry()
    if args.json:
        print(json.dumps(reg, indent=2))
        return 0
    for mode in ("generate", "edit"):
        print(f"{mode} (* = default):")
        for m, s in reg.items():
            if mode in s:
                sp = s[mode]
                price = f"~${sp['price']:.3f}" if "price" in sp else "   price?"
                print(f"  {'*' if sp.get('default') else ' '} {m:24} {price}  "
                      f"{sp['endpoint']:44} {s.get('note', '') if mode == 'generate' else ''}")
        print()
    print("Add or override models in ~/.config/falg/models.json or a config's \"model_defs\".")
    from .catalog import staleness_note
    print(staleness_note())
    return 0


def cmd_catalog(args) -> int:
    from .catalog import run_cli
    return run_cli(args)


def cmd_search(args) -> int:
    rows = fal.search_models(args.query, args.limit, args.category)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        md = r.get("metadata", {})
        print(f"{r['endpoint_id']:52} {md.get('category', ''):18} {(md.get('date') or '')[:10]}  "
              f"{md.get('display_name', '')}")
    return 0


def _type(p: dict, all_schemas: dict) -> str:
    if "$ref" in p:
        return p["$ref"].rsplit("/", 1)[-1]
    if "enum" in p:
        return "|".join(map(str, p["enum"]))
    if "anyOf" in p:
        return " or ".join(_type(x, all_schemas) for x in p["anyOf"] if x.get("type") != "null")
    if p.get("type") == "array":
        return f"list[{_type(p.get('items', {}), all_schemas)}]"
    return p.get("type", "?")


def cmd_schema(args) -> int:
    info = fal.input_schema(args.endpoint)
    if args.json:
        print(json.dumps(info["schema"], indent=2))
        return 0
    s = info["schema"]
    req = set(s.get("required", []))
    print(f"{args.endpoint}  ({info['name']})")
    for name, p in s.get("properties", {}).items():
        default = f" = {json.dumps(p['default'])}" if "default" in p else ""
        desc = " ".join((p.get("description") or "").split())
        print(f"  {'*' if name in req else ' '} {name}: {_type(p, info['all'])}{default}")
        if desc:
            print(f"      {desc[:160]}")
    for name, sch in info["all"].items():  # referenced object types (e.g. ImageSize)
        if name != info["name"] and "properties" in sch and not name.endswith(("Output", "Status")):
            print(f"  [{name}] " + ", ".join(f"{k}: {_type(v, info['all'])}"
                                            for k, v in sch["properties"].items()))
    return 0


def cmd_auth(args) -> int:
    if args.remove:
        env = fal.save_key(None)
        print(f"Removed FAL_KEY from {env}")
    elif args.status:
        pass
    else:
        key = args.key
        if key in (None, "-"):
            if key is None and sys.stdin.isatty():
                import getpass
                key = getpass.getpass("fal API key (input hidden): ")
            else:
                key = sys.stdin.readline()
        key = (key or "").strip().strip("'\"")
        if not key:
            raise SystemExit("no key given")
        env = fal.save_key(key)
        print(f"Saved {fal.mask(key)} to {env} (readable only by you)")
    key, source = fal.find_key_source()
    if key:
        print(f"Active key here: {fal.mask(key)} from {source}")
        global_env = fal.CONFIG_DIR / ".env"
        if source != str(global_env) and global_env.is_file() and "FAL_KEY=" in global_env.read_text(encoding="utf-8"):
            log("note: this overrides the global key in ~/.config/falg/.env "
                "(env var and ./.env take precedence)")
    else:
        print("No key found. Run `falg auth` to save one.")
    return 0


def cmd_cutout(args) -> int:
    from .cutout import run_cli
    return run_cli(args)


# --------------------------------------------------------------------------- parser


def _doc(module_file: str) -> str:
    """A module's docstring without importing it (cutout pulls in numpy/scipy)."""
    import ast
    from importlib import resources
    return ast.get_docstring(ast.parse(resources.files("falg").joinpath(module_file).read_text(encoding="utf-8"))) or ""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="falg", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"falg {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND")

    def common(p):
        p.add_argument("-m", "--models", nargs="+", help="model names (see `falg models`)")
        p.add_argument("-n", type=int, help="images per prompt per model")
        p.add_argument("-a", "--aspect", help="e.g. 1:1, 3:2, 2:3, 16:9 (edits default to auto)")
        p.add_argument("-o", "--out", help="parent output dir (default ./generations)")
        p.add_argument("--dry-run", action="store_true", help="print prompts and cost, send nothing")
        p.add_argument("-y", "--yes", action="store_true", help="skip the cost confirmation")
        p.add_argument("--max-cost", type=float, help="approve runs up to this estimate (USD) without asking; abort above it")
        p.add_argument("--workers", type=positive_int, default=6, help="parallel requests (default 6)")
        p.add_argument("--json", action="store_true", help="print a JSON summary (files, sidecars)")

    p = sub.add_parser("run", help="run a JSON job config")
    p.add_argument("config")
    p.add_argument("--only", nargs="+", metavar="AXIS=A,B", help="restrict axes, e.g. style=riso,chalk")
    p.add_argument("--set", nargs="+", metavar="VAR=TEXT", help="override a constant variable")
    common(p)
    p.set_defaults(func=cmd_run)

    for name, help_ in (("gen", "quick generation from a prompt"), ("edit", "edit an image")):
        p = sub.add_parser(name, help=help_)
        if name == "edit":
            p.add_argument("source", help="image file or URL")
        p.add_argument("prompt")
        p.add_argument("-i", "--image", nargs="+", help="input image(s) -> uses edit endpoints")
        p.add_argument("-p", "--param", nargs="+", metavar="K=V", help="extra args (k=v, k:=json)")
        p.add_argument("--name", help="label for the output folder")
        common(p)
        p.set_defaults(func=cmd_edit if name == "edit" else cmd_gen)

    p = sub.add_parser("call", help="call any fal endpoint with raw args")
    p.add_argument("endpoint")
    p.add_argument("kv", nargs="*", metavar="K=V", help="k=v strings, k:=json values")
    p.add_argument("--args", help="JSON file with the request body ('-' for stdin)")
    p.add_argument("--file", action="append", metavar="KEY=PATH",
                   help="send a local file as a data URI (repeat for several files)")
    p.add_argument("--name")
    p.add_argument("-o", "--out")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_call)

    p = sub.add_parser("auth", help="save your fal API key (~/.config/falg/.env)",
                       description="Save the fal API key for all projects. Without KEY it asks "
                       "with hidden input (keeps the key out of shell history); '-' reads stdin. "
                       "Lookup order: FAL_KEY env var, ./.env, the config's dir, ~/.config/falg/.env.")
    p.add_argument("key", nargs="?", help="the key (prefer omitting it: you'll be asked, hidden)")
    p.add_argument("--status", action="store_true", help="show which key is active and where from")
    p.add_argument("--remove", action="store_true", help="delete the saved global key")
    p.set_defaults(func=cmd_auth)

    p = sub.add_parser("models", help="list the model registry")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("catalog", help="write a dated snapshot of recent fal models to MODELS.md")
    p.add_argument("--days", type=int, default=180, help="list models released in the last N days")
    p.add_argument("--categories", nargs="+", default=["text-to-image", "image-to-image"],
                   help="fal categories (e.g. text-to-video, image-to-video, text-to-speech)")
    p.add_argument("-o", "--out", help="output file (default: MODELS.md in the falg repo)")
    p.add_argument("--no-prices", action="store_true")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("search", help="search fal's model catalog")
    p.add_argument("query")
    p.add_argument("--category", help="e.g. text-to-image, image-to-image, text-to-video")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("schema", help="show an endpoint's input parameters")
    p.add_argument("endpoint")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("cutout", help="remove white/black background -> print-ready PNG",
                       description=_doc("cutout.py"),
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("inputs", nargs="+", type=Path)
    p.add_argument("-o", "--out", type=Path, required=True)
    p.add_argument("--bg", choices=["white", "black"], default="white",
                   help="background to remove (white: art on white; black: light art on black)")
    p.add_argument("--fit", type=float, nargs=2, metavar=("W", "H"),
                   help="resize to fit W x H cm at --ppi (adds __WxHcm to the name)")
    p.add_argument("--ppi", type=int, default=300)
    p.add_argument("--names", nargs="+", help="output base names, same order as inputs")
    p.add_argument("--suffix", help="name suffix, e.g. light-shirt")
    p.add_argument("--ink", help='recolour everything kept to one colour, e.g. "#FF2D95"')
    p.add_argument("--low", type=float, default=0.10, help="levels: at/below = transparent (0-1)")
    p.add_argument("--high", type=float, default=0.60, help="levels: at/above = solid (0-1)")
    p.add_argument("--soft", action="store_true", help="graded alpha instead of hard 0/255")
    p.add_argument("--min-speck", type=int, default=6, help="drop isolated marks smaller than N px")
    p.add_argument("--min-line-mm", type=float, default=0.3, help="report ink thinner than this")
    p.add_argument("--pad", type=int, default=8, help="padding around the crop, source px")
    p.add_argument("--no-crop", action="store_true", help="keep the full canvas")
    p.add_argument("--no-preview", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_cutout)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # bare `falg`: show what it can do instead of a usage error
        ap.print_help()
        return 0
    runner.abandoned.clear()
    fal.reset_submitted()  # counts are per command (tests and long-lived callers run several)
    args, extra = ap.parse_known_args(argv)
    if extra:
        # `call ENDPOINT --json k=v`: before Python 3.12, argparse fills the k=v positional
        # (empty) before the option, and leaves later k=v arguments over
        if args.cmd == "call" and all("=" in x and not x.startswith("-") for x in extra):
            args.kv = [*args.kv, *extra]
        else:
            ap.error(f"unrecognized arguments: {' '.join(extra)}")
    try:
        return args.func(args) or 0
    except (ValueError, OSError, fal.FalError) as e:  # OSError: missing files, network, disk
        log(f"error: {e}")
        return 1
    except KeyboardInterrupt:
        n = fal.submitted_count()  # only warn about running jobs if something was actually sent
        log("\ninterrupted" + (f"; {n} request(s) already sent keep running on fal and are billed "
                               "(request ids are in run.json / result.json)" if n else ""))
        if runner.abandoned.is_set():
            # run.json and the gallery are saved; don't wait for workers stuck in a download
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(130)
        return 130


if __name__ == "__main__":
    sys.exit(main())
