"""Model registry and job planning: a JSON config -> a list of fal requests."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from importlib import resources
from pathlib import Path

from . import fal
from .fal import as_url

# --------------------------------------------------------------------------- registry


def _deep_merge(base: dict, extra: dict) -> dict:
    """Nested objects merge key by key, so overriding one param keeps the built-in ones;
    a null value removes a built-in key."""
    out = dict(base)
    for k, v in extra.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def strip_notes(x):
    """Copy without keys starting with "_": they are notes, at any level of a config."""
    if isinstance(x, dict):
        return {k: strip_notes(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, list):
        return [strip_notes(v) for v in x]
    return x


def load_registry(extra: dict | None = None) -> dict:
    reg = json.loads(resources.files("falg").joinpath("models.json").read_text(encoding="utf-8"))
    reg = strip_notes(reg)
    user = fal.CONFIG_DIR / "models.json"
    if user.is_file():
        reg = _deep_merge(reg, strip_notes(json.loads(user.read_text(encoding="utf-8"))))
    if extra:
        reg = _deep_merge(reg, strip_notes(extra))
    return reg


def default_models(reg: dict, mode: str) -> list[str]:
    return [m for m, s in reg.items() if s.get(mode, {}).get("default")]


def _ratio(aspect: str) -> float:
    a, _, b = aspect.partition(":")
    try:
        w, h = float(a), float(b or 1)
    except ValueError:
        w = h = 0.0
    if not (w > 0 and h > 0 and math.isfinite(w / h)):
        raise ValueError(f"aspect must look like W:H with positive numbers (e.g. 3:2), got {aspect!r}")
    return w / h


def size_args(spec: dict, aspect: str | None, source_size: tuple[int, int] | None = None) -> dict:
    """source_size: (w, h) of the first input image, used by px models when aspect is "auto"."""
    mode = spec.get("size", "none")
    if mode == "px":
        if aspect == "auto":
            if not (source_size and all(source_size)):  # unknown input size (URL): let the endpoint pick
                return {}
            aspect = f"{source_size[0]}:{source_size[1]}"
        r, px, m = _ratio(aspect or "1:1"), spec["pixels"], spec.get("multiple", 16)
        w, h = int(math.sqrt(px * r) // m * m), int(math.sqrt(px / r) // m * m)
        return {spec.get("size_param", "image_size"): {"width": w, "height": h}}
    if mode == "aspect":
        return {"aspect_ratio": aspect} if aspect else {}
    if mode == "enum":
        enum = spec.get("enum_map", {})
        value = enum.get(aspect or "1:1")
        if value is None:
            raise ValueError(f"aspect {aspect} not available; choose from {', '.join(enum)}")
        return {spec.get("size_param", "image_size"): value}
    return {}


def build_args(spec: dict, prompt: str, count: int, aspect: str | None,
               images: list[str], overrides: dict,
               source_size: tuple[int, int] | None = None) -> dict:
    args: dict = {"prompt": prompt}
    args.update(size_args(spec, aspect, source_size))
    args.update(spec.get("params", {}))
    if images:
        args[spec.get("image_param", "image_urls")] = images
    if spec.get("batch") and count > 1:
        args["num_images"] = count
    for k, v in overrides.items():  # null removes a key, as it does in model_defs
        if v is None:
            args.pop(k, None)
        else:
            args[k] = v
    return args


# --------------------------------------------------------------------------- prompts

VAR = re.compile(r"\{([A-Za-z_][\w-]*)\}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")  # model names go into file names
# file name = <label>__<model>__<index><ext>: 120 + 2 + 64 + 2 + 5 + len(".sidecar.json") < 255
MAX_LABEL = 120
DEFAULT_MAX_BATCH = 4  # num_images cap assumed for batch models without "max_batch"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9.]+", "-", s.lower()).strip("-")[:48] or "x"


def _text(v) -> str:
    return " ".join(str(x) for x in v) if isinstance(v, list) else str(v)


def render(template: str, values: dict[str, str]) -> str:
    out = template
    for _ in range(8):  # variables may reference other variables
        new = VAR.sub(lambda m: values.get(m.group(1), m.group(0)), out)
        if new == out:
            break
        out = new
    return re.sub(r"\s+", " ", out).strip()


def combos(cfg: dict, only: dict[str, set[str]] | None = None) -> list[dict]:
    """Expand vars into prompt combinations.

    vars: a string (or list of strings, joined) is a constant; an object is an AXIS of named
    options, and every combination of axes becomes one prompt. An option is a string, or
    {"text": ..., "set": {var: value}} to override other variables for that option.
    """
    variables = dict(cfg.get("vars", {}))
    if "prompts" in cfg:
        p = cfg["prompts"]
        if not isinstance(p, (list, dict)):  # a string would be split into one prompt per character
            raise ValueError(f"prompts must be a list or an object, got {type(p).__name__}; "
                             "use \"prompt\" for a single prompt")
        variables["prompt"] = p if isinstance(p, dict) else {f"p{i:02d}": t for i, t in enumerate(p, 1)}
    elif "prompt" in cfg:
        variables["prompt"] = cfg["prompt"]
    template = _text(cfg.get("template", "{prompt}"))

    consts = {k: _text(v) for k, v in variables.items() if not isinstance(v, dict)}
    axes = {k: v for k, v in variables.items() if isinstance(v, dict)}
    for k, wanted in (only or {}).items():
        if k not in axes:
            raise ValueError(f"--only {k}: not an axis (axes: {', '.join(axes) or 'none'})")
        missing = wanted - set(axes[k])
        if missing:
            raise ValueError(f"--only {k}: unknown option(s) {', '.join(sorted(missing))}; "
                             f"have {', '.join(axes[k])}")
        axes[k] = {n: v for n, v in axes[k].items() if n in wanted}

    out, seen = [], {}
    for picks in itertools.product(*[list(opts.items()) for opts in axes.values()]):
        values, overrides, names = dict(consts), {}, {}
        for axis, (name, opt) in zip(axes, picks):
            names[axis] = name
            if isinstance(opt, dict):
                values[axis] = _text(opt.get("text", ""))
                overrides.update({k: _text(v) for k, v in opt.get("set", {}).items()})
            else:
                values[axis] = _text(opt)
        values.update(overrides)
        label = "__".join(slug(n) for n in names.values()) or "image"
        if len(label) > MAX_LABEL:  # keep file names under filesystem limits; hash keeps it unique
            label = label[:MAX_LABEL - 9].rstrip("-_") + "-" + hashlib.sha1(label.encode()).hexdigest()[:8]
        if label in seen:  # file names derive from the label: a clash would overwrite paid outputs
            raise ValueError(f"options {seen[label]} and {names} both become file label {label!r}; "
                             "rename one (labels use a-z, 0-9, '.' and '-', max 48 chars)")
        seen[label] = names
        prompt = render(template, values)
        leftover = sorted(set(VAR.findall(prompt)))  # undefined, cyclic or nested too deep
        out.append({"label": label, "vars": names, "prompt": prompt, "unresolved": leftover})
    return out


# --------------------------------------------------------------------------- jobs


def plan(cfg: dict, base_dir: Path, *, models: list[str] | None = None, n: int | None = None,
         aspect: str | None = None, only: dict[str, set[str]] | None = None,
         images: list[str] | None = None) -> tuple[list[dict], dict]:
    cfg = strip_notes(cfg)
    reg = load_registry(cfg.get("model_defs"))
    srcs = images if images is not None else cfg.get("images", [])
    if not isinstance(srcs, list):  # a string would be split into one image per character
        raise ValueError(f"images must be a list, got {type(srcs).__name__}")
    srcs = [s if str(s).startswith(("http://", "https://", "data:"))
            else str((base_dir / Path(s).expanduser()).resolve()) for s in srcs]  # ~ before joining
    for s in srcs:
        if not s.startswith(("http://", "https://", "data:")) and not Path(s).is_file():
            raise ValueError(f"image not found: {s}")
    mode = "edit" if srcs else "generate"
    models = models or cfg.get("models") or default_models(reg, mode)
    if not isinstance(models, list):  # a string would be split into one model per character
        raise ValueError(f"models must be a list, got {type(models).__name__}")
    n = n if n is not None else cfg.get("n", 1)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 9999:
        raise ValueError(f"n must be an integer from 1 to 9999, got {n!r}")
    aspect = aspect or cfg.get("aspect") or (None if mode == "edit" else "1:1")
    if mode == "edit" and not aspect:
        aspect = "auto"
    if aspect != "auto":
        _ratio(aspect)  # a bad aspect is an error before anything is sent
    source_size = None
    if srcs and not srcs[0].startswith(("http://", "https://", "data:")):
        source_size = fal.image_size(Path(srcs[0]))
    params = cfg.get("params", {})
    for scope, over in params.items():
        if not isinstance(over, dict):
            raise ValueError(f"params[{scope!r}] must be an object of request arguments")
        if scope != "*" and scope not in reg:  # a typo would silently drop these params
            raise ValueError(f"params[{scope!r}]: unknown model; use \"*\" or a model name "
                             "(see `falg models`)")
        if "prompt" in over:  # the recorded prompt (sidecars, gallery, dry-run) must be what is sent
            raise ValueError(f"params[{scope!r}] sets 'prompt'; use prompt/prompts/template/vars instead")

    # names go into file names, and macOS/Windows file names ignore case: flux-3 and Flux-3 would
    # overwrite each other's outputs
    lowered = [m.lower() for m in models]
    dupes = sorted({m for m in models if lowered.count(m.lower()) > 1})
    if dupes:
        raise ValueError(f"model(s) listed more than once (ignoring case): {', '.join(dupes)} "
                         "(use n for more images)")
    for m in models:
        if not SAFE_NAME.fullmatch(m):
            raise ValueError(f"model name {m!r} must be file-name safe (letters, digits, '.', '_', '-'; "
                             "at most 64 characters); "
                             "it is used in output file names")
        if m not in reg:
            raise ValueError(f"unknown model {m!r}; see `falg models` or add it under model_defs")
        if mode not in reg[m]:
            raise ValueError(f"model {m!r} has no {mode} endpoint")
        if "prompt" in reg[m][mode].get("params", {}):  # would replace the rendered prompt
            raise ValueError(f"model {m!r}: {mode} params set 'prompt'; "
                             "use prompt/prompts/template/vars instead")
    urls = [as_url(s) for s in srcs]

    jobs = []
    for c in combos(cfg, only):
        for m in models:
            spec = reg[m][mode]
            over = {**params.get("*", {}), **params.get(m, {})}
            if spec.get("batch"):  # endpoints cap num_images: split n into requests of <= max_batch
                cap = spec.get("max_batch", DEFAULT_MAX_BATCH)
                if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
                    raise ValueError(f"{m}: max_batch must be a positive integer, got {cap!r}")
                counts = [cap] * (n // cap) + ([n % cap] if n % cap else [])
            else:
                counts = [1] * n
            index = 1
            for k in counts:
                args = build_args(spec, c["prompt"], k, aspect, urls, over, source_size)
                seed = args.get("seed")
                if isinstance(seed, str) and seed.strip().lstrip("-").isdigit():  # -p seed=7
                    seed = int(seed)
                if len(counts) > 1 and isinstance(seed, int) and not isinstance(seed, bool):
                    # the same seed in every request would buy the same images again
                    args["seed"] = seed + index - 1
                # the effective count is what is actually sent (params may override num_images)
                k = args.get("num_images", k)
                if isinstance(k, bool) or not isinstance(k, int) or k < 1:
                    raise ValueError(f"{m}: num_images must be a positive integer, got {k!r}")
                jobs.append({
                    "label": c["label"], "vars": c["vars"], "model": m, "mode": mode,
                    "endpoint": spec["endpoint"], "index": index, "count": k,
                    # None = unknown: the cost check must not treat an unpriced model as free
                    "price": spec["price"] * k if "price" in spec else None, "prompt": c["prompt"],
                    "unresolved": c["unresolved"], "sources": srcs, "args": args,
                })
                index += k
    return jobs, {"mode": mode, "models": models, "n": n, "aspect": aspect}
