"""`falg catalog`: write a dated snapshot of fal's recent models to MODELS.md.

The point: model names and versions change monthly, so never pick a model from memory.
Read MODELS.md (check its date) or refresh it with `falg catalog`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import fal
from .plan import load_registry

DEFAULT_CATEGORIES = ["text-to-image", "image-to-image"]
STALE_DAYS = 30


def default_path() -> Path:
    """MODELS.md in the falg repo (editable install), else the current directory."""
    root = Path(__file__).resolve().parents[2]
    return root / "MODELS.md" if (root / "pyproject.toml").is_file() else Path.cwd() / "MODELS.md"


def snapshot_date(path: Path | None = None) -> date | None:
    path = path or default_path()
    if not path.is_file():
        return None
    m = re.search(r"Generated: (\d{4}-\d{2}-\d{2})", path.read_text(encoding="utf-8")[:600])
    return date.fromisoformat(m.group(1)) if m else None


def staleness_note(path: Path | None = None) -> str:
    d = snapshot_date(path)
    if d is None:
        return "No model catalog snapshot yet: run `falg catalog`."
    age = (date.today() - d).days
    note = f"Catalog snapshot (MODELS.md): {d} ({age} day(s) old)"
    return note + (" -- STALE, run `falg catalog`" if age > STALE_DAYS else "")


def family(name: str, spec: dict) -> str:
    """Family keyword used to spot newer releases: 'seedream-5-pro' -> 'seedream'."""
    return spec.get("family") or re.sub(r"[-.]?(v?\d.*)$", "", name).split("-vector")[0]


def _price(p: dict | None) -> str:
    if not p:
        return ""
    unit = p.get("unit", "")
    return f"${p['unit_price']:g} / {unit}".rstrip(" /")


def _cell(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ")


def build(key: str | None, *, days: int, categories: list[str], with_prices: bool) -> tuple[str, dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows: dict[str, list[dict]] = {}
    everything: dict[str, dict] = {}
    for cat in categories:
        fal_rows = fal.list_models(cat, key)
        for r in fal_rows:
            everything[r["endpoint_id"]] = r
        rows[cat] = sorted(
            (r for r in fal_rows if (r["metadata"].get("date") or "")[:10] >= since
             and r["metadata"].get("status", "active") == "active"),
            key=lambda r: r["metadata"].get("date") or "", reverse=True)

    reg = load_registry()
    reg_endpoints = {sp["endpoint"] for s in reg.values() for k, sp in s.items() if isinstance(sp, dict)
                     and "endpoint" in sp}
    price = {}
    if with_prices and key:
        wanted = sorted({r["endpoint_id"] for rs in rows.values() for r in rs} | reg_endpoints)
        try:
            price = fal.prices(wanted, key)
        except fal.FalError as e:  # prices are a bonus
            print(f"warning: pricing API failed: {e}")

    today = date.today().isoformat()
    out = [
        "# fal.ai model catalog snapshot",
        "",
        f"Generated: {today} by `falg catalog` (released since {since}; "
        f"categories: {', '.join(categories)}).",
        "",
        "> **Don't pick models from memory**: names and versions change every month. Use this",
        f"> file if it is fresh (under {STALE_DAYS} days old); otherwise run `falg catalog` first.",
        "> Check an endpoint's inputs with `falg schema <endpoint>` before adding it to the registry.",
        "",
        "Prices come from fal's pricing API, as reported (`unit` varies: per image, per",
        "megapixel, or fal's generic `units`). Confirm on the model page before relying on them.",
        "",
        "## Registry check",
        "",
        "These are the models falg knows (`src/falg/models.json`). The last column lists newer",
        "catalog entries from the same family; consider upgrading to them.",
        "",
        "| registry name | mode | endpoint | released | price | newer in family |",
        "|---|---|---|---|---|---|",
    ]
    for name, s in reg.items():
        fam = family(name, s)
        for mode in ("generate", "edit"):
            sp = s.get(mode)
            if not sp:
                continue
            ep = sp["endpoint"]
            r = everything.get(ep)
            released = (r["metadata"].get("date") or "")[:10] if r else "not in catalog"
            cat = r["metadata"].get("category") if r else None
            newer = sorted(
                (x for x in everything.values()
                 if fam in x["endpoint_id"] and x["endpoint_id"] != ep
                 and (cat is None or x["metadata"].get("category") == cat)
                 and (x["metadata"].get("date") or "")[:10] > (released if r else "")
                 and x["metadata"].get("status", "active") == "active"),
                key=lambda x: x["metadata"].get("date") or "", reverse=True)[:4]
            newer_txt = ", ".join(f"`{x['endpoint_id']}` ({(x['metadata'].get('date') or '')[:10]})"
                                  for x in newer)
            out.append(f"| {name} | {mode} | `{ep}` | {released} | {_cell(_price(price.get(ep)))} "
                       f"| {newer_txt} |")

    for cat, rs in rows.items():
        out += ["", f"## {cat}: {len(rs)} released since {since}", "",
                "| released | endpoint | name | price | in registry |", "|---|---|---|---|---|"]
        for r in rs:
            md = r["metadata"]
            ep = r["endpoint_id"]
            out.append(f"| {(md.get('date') or '')[:10]} | `{ep}` | {_cell(md.get('display_name', ''))} "
                       f"| {_cell(_price(price.get(ep)))} | {'yes' if ep in reg_endpoints else ''} |")
    out.append("")
    stats = {"since": since, **{c: len(r) for c, r in rows.items()}, "prices": len(price)}
    return "\n".join(out), stats


def run_cli(args) -> int:
    key = fal.find_key()
    if not key:
        print("note: no FAL_KEY; anonymous catalog requests are rate-limited and prices are skipped")
    path = Path(args.out) if args.out else default_path()
    text, stats = build(key, days=args.days, categories=args.categories, with_prices=not args.no_prices)
    path.write_text(text, encoding="utf-8")
    print(f"Wrote {path} at {datetime.now():%Y-%m-%d %H:%M}: " +
          ", ".join(f"{k} {v}" for k, v in stats.items()))
    return 0
