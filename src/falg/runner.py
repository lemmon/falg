"""Execute planned jobs in parallel, download outputs, write sidecars, run.json and a gallery."""

from __future__ import annotations

import html
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from . import fal


def log(*a) -> None:
    print(*a, file=sys.stderr, flush=True)


def make_run_dir(parent: Path, name: str) -> Path:
    base = parent / f"{datetime.now():%Y%m%d-%H%M%S}-{name}"
    out, n = base, 1
    while True:  # parallel runs started in the same second get -2, -3, ...
        try:
            out.mkdir(parents=True)
            return out
        except FileExistsError:
            n += 1
            out = base.with_name(f"{base.name}-{n}")


# set when the user stops waiting (second Ctrl+C) while workers may still be inside a network call
# that can't be interrupted (a download can take minutes); the CLI then exits without joining them
abandoned = threading.Event()


class JobError(Exception):
    """A failed job, with whatever was learned before the failure (request id, URLs, files)."""

    def __init__(self, message: str, partial: dict):
        super().__init__(message)
        self.partial = partial


def _run_one(job: dict, key: str, out_dir: Path, run_info: dict,
             on_submit=None, cancel: threading.Event | None = None,
             no_submit: threading.Event | None = None) -> dict:
    """Runs in a worker thread. Reads `job` but never mutates it (the main thread snapshots
    jobs to run.json concurrently); returns the updates instead. On failure raises JobError
    carrying the request id and output URLs, so a paid result can still be recovered."""
    partial: dict = {}
    try:
        return _run_one_inner(job, key, out_dir, run_info, partial, on_submit, cancel, no_submit)
    except Exception as e:
        raise JobError(str(e), partial) from e


def _run_one_inner(job: dict, key: str, out_dir: Path, run_info: dict, partial: dict,
                   on_submit=None, cancel: threading.Event | None = None,
                   no_submit: threading.Event | None = None) -> dict:
    t0 = datetime.now()

    def submitted(info: dict) -> None:
        partial.update(info)
        if on_submit:
            on_submit(job, info)

    rid, result = fal.run(job["endpoint"], job["args"], key, on_submit=submitted, cancel=cancel,
                          no_submit=no_submit)
    seed = result.get("seed")
    media = fal.media_in(result)
    partial.update(request_id=rid, seed=seed, output_urls=[f["url"] for f in media])
    if not media:
        raise fal.FalError(f"no files in response (request {rid}): {json.dumps(result)[:400]}")
    files = partial.setdefault("files", [])
    for i, f in enumerate(media):
        if cancel is not None and cancel.is_set():
            raise fal.Cancelled(f"stopped before downloading (request {rid}; outputs: see output_urls)")
        # this job owns indexes index .. index+count-1; files beyond `count` (a mask, a second
        # copy...) get a sub-number instead, so they can't take another job's file names
        num = f"{job['index'] + i:02d}" if i < job["count"] else f"{job['index']:02d}-{i + 1}"
        stem = f"{job['label']}__{job['model']}__{num}"
        name = stem + fal.ext_for(f)
        fal.download(f["url"], out_dir / name)
        if not (f.get("width") and f.get("height")):
            wh = fal.image_size(out_dir / name)
            if wh:
                f = {**f, "width": wh[0], "height": wh[1]}
        entry = {"file": name, "sidecar": fal.sidecar_name(name), "width": f.get("width"),
                 "height": f.get("height"), "content_type": f.get("content_type"), "url": f["url"]}
        sidecar = {
            "file": name, "created": t0.isoformat(timespec="seconds"),
            "seconds": round((datetime.now() - t0).total_seconds(), 1),
            "model": job["model"], "mode": job["mode"], "endpoint": job["endpoint"],
            "vars": job["vars"], "prompt": job["prompt"],
            "sources": fal.elide_data(job["sources"]), "seed": seed, "request_id": rid,
            "width": f.get("width"), "height": f.get("height"),
            "content_type": f.get("content_type"), "url": f["url"],
            "price_estimate": (round(job["price"] / max(len(media), 1), 4)
                               if job["price"] is not None else None),
            "args": fal.elide_data(job["args"]),
            "response": fal.elide_data({k: v for k, v in result.items() if k not in ("images", "image")}),
            **run_info,
        }
        (out_dir / entry["sidecar"]).write_text(json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(entry)
    return {"request_id": rid, "seed": seed, "files": files}


def execute(jobs: list[dict], key: str, out_dir: Path, meta: dict, workers: int = 6) -> int:
    run_info = {"run": out_dir.name, "config": meta.get("config_path")}

    lock = threading.RLock()  # guards job dicts and run.json (workers record submissions too)
    cancel = threading.Event()     # second Ctrl+C: stop waiting for submitted jobs
    no_submit = threading.Event()  # first Ctrl+C: send nothing more (incl. workers backing off)

    def save() -> None:
        with lock:
            snapshot = json.dumps({**meta, "jobs": [fal.elide_data(j) for j in jobs]},
                                  indent=2, ensure_ascii=False)
            tmp = out_dir / ".run.json.tmp"
            tmp.write_text(snapshot, encoding="utf-8")
            tmp.replace(out_dir / "run.json")

    def on_submit(job: dict, info: dict) -> None:  # worker thread: persist the request id at once
        with lock:
            job.update(info)
            save()

    failures = 0
    handled: set = set()

    def handle(fut) -> None:  # main thread only: apply a finished worker's result to its job
        nonlocal failures
        handled.add(fut)
        j = futures[fut]
        label = f"{j['label']} / {j['model']}"
        try:
            result = fut.result()
            with lock:
                j.update(result)
            log(f"  ok    {label}: {', '.join(f['file'] for f in j['files'])}")
        except Exception as e:  # keep going; record the failure and anything recoverable
            failures += 1
            with lock:
                if isinstance(e, JobError):
                    j.update(e.partial)
                j["error"] = str(e)
            log(f"  FAIL  {label}: {e}" + (f" (request {j['request_id']})" if j.get("request_id") else ""))
        save()

    save()
    pool = ThreadPoolExecutor(max_workers=workers)
    futures: dict = {}
    try:
        for j in jobs:  # inside the try: a Ctrl+C while queueing must cancel what is queued
            futures[pool.submit(_run_one, j, key, out_dir, run_info, on_submit, cancel, no_submit)] = j
        for fut in as_completed(futures):
            handle(fut)
    except KeyboardInterrupt:
        # stop jobs that haven't been sent: queued ones, and workers not yet past the POST
        no_submit.set()
        pool.shutdown(wait=False, cancel_futures=True)
        started = {id(j) for f, j in futures.items() if not f.cancelled()}
        with lock:
            for j in jobs:
                if id(j) not in started:
                    j["error"] = "cancelled (interrupted before submission)"
        running = [f for f in futures if not f.cancelled() and f not in handled]
        with lock:
            sent = sum(1 for f in running if futures[f].get("request_id"))
        log(f"\ninterrupted: {len(jobs) - len(started)} queued job(s) cancelled; nothing more will be "
            f"sent. Waiting for {sent} submitted request(s)"
            + (f" and {len(running) - sent} job(s) still sending or about to stop" if len(running) > sent else "")
            + " (Ctrl+C again to stop waiting)")
        save()
        try:
            for fut in as_completed(running):
                handle(fut)
        except KeyboardInterrupt:
            cancel.set()  # workers stop polling and skip downloads at the next chance
            no_submit.set()
            abandoned.set()
            with lock:
                for fut in running:
                    if fut not in handled:
                        futures[fut]["error"] = ("abandoned while running; the request may still "
                                                 "finish on fal (see request_id / response_url)")
            log("stopped waiting")
        save()
        write_gallery(out_dir, jobs, meta)
        raise
    except BaseException:
        # any other error (e.g. run.json can't be written): without this, the executor would go
        # on submitting every queued job, each one paid, while Python shuts down
        no_submit.set()  # and running workers: send nothing more, stop polling
        cancel.set()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    write_gallery(out_dir, jobs, meta)
    return failures


# a CSS colour goes into index.html's <style> unescaped, so accept only colour syntax: #hex, a
# keyword, or a colour function. No url(...), no ; { } < >, so a shared config can't load a URL,
# add rules or close the <style>.
CSS_COLOUR = re.compile(r"#[0-9A-Fa-f]{3,8}|[A-Za-z]{3,20}"
                        r"|(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\([\w\s.,%/+-]{1,48}\)")


def check_background(value) -> str:
    if not isinstance(value, str) or not CSS_COLOUR.fullmatch(value):
        raise ValueError(f"gallery_background must be a CSS colour like \"#888\" or \"white\", got {value!r}")
    return value


def write_gallery(out_dir: Path, jobs: list[dict], meta: dict) -> None:
    labels = list(dict.fromkeys(j["label"] for j in jobs))
    models = list(dict.fromkeys(j["model"] for j in jobs))
    prompts = {j["label"]: j["prompt"] for j in jobs}
    cells: dict[tuple[str, str], list[str]] = {}
    for j in jobs:
        bucket = cells.setdefault((j["label"], j["model"]), [])
        for f in j.get("files", []):
            q = html.escape(f["file"])
            if (f.get("content_type") or "").startswith("video") or q.endswith((".mp4", ".webm")):
                media = f'<video src="{q}" controls loop muted></video>'
            elif (f.get("content_type") or "").startswith("image") or q.endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")):
                media = f'<a href="{q}" target="_blank"><img src="{q}" loading="lazy"></a>'
            else:
                media = ""
            bucket.append(f'{media}<small><a href="{q}">{q}</a></small>')
        if j.get("error"):
            bucket.append(f'<p class="err">{html.escape(j["error"][:400])}</p>')

    head = "".join(f"<th>{html.escape(m)}</th>" for m in models)
    rows = "".join(
        f'<tr><th title="{html.escape(prompts[lb])}">{html.escape(lb)}</th>'
        + "".join(f"<td>{''.join(cells.get((lb, m), []))}</td>" for m in models) + "</tr>"
        for lb in labels)
    bg = meta.get("gallery_background", "#888")
    if not (isinstance(bg, str) and CSS_COLOUR.fullmatch(bg)):  # checked before the run, too
        bg = "#888"
    (out_dir / "index.html").write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(out_dir.name)}</title>
<style>
 body {{ font: 14px system-ui, sans-serif; margin: 16px; background: {bg}; }}
 table {{ border-collapse: collapse; }}
 th, td {{ border: 1px solid #6668; padding: 6px; vertical-align: top; }}
 thead th {{ position: sticky; top: 0; background: #ddd; }}
 tbody th {{ background: #ddd; writing-mode: vertical-rl; transform: rotate(180deg); cursor: help; }}
 img, video {{ width: 300px; display: block; }}
 small {{ display: block; margin-bottom: 8px; background: #ddd; padding: 2px 4px; }} small a {{ color: #111; }}
 .err {{ width: 300px; color: #700; background: #fee; padding: 6px; }}
 .bar button {{ margin-right: 4px; }}
</style></head><body>
<p class="bar">Page background:
 <button onclick="document.body.style.background='#888'">grey</button>
 <button onclick="document.body.style.background='#fff'">white</button>
 <button onclick="document.body.style.background='#111'">black</button>
 &nbsp; Hover a row label for its prompt; each image has a .json sidecar next to it.</p>
<table><thead><tr><th></th>{head}</tr></thead><tbody>{rows}</tbody></table>
</body></html>
""", encoding="utf-8")
