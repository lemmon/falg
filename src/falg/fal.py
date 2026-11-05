"""Minimal fal.ai client: key lookup, queue submit/poll/result, media download. Standard library only."""

from __future__ import annotations

import base64
import http.client
import json
import mimetypes
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

from . import __version__

QUEUE_BASE = "https://queue.fal.run"
CONFIG_DIR = Path(os.environ.get("FALG_HOME", Path.home() / ".config" / "falg"))
UA = {"User-Agent": f"falg/{__version__}"}


def find_key_source(extra_dirs: Iterable[Path] = ()) -> tuple[str | None, str | None]:
    """(key, where it came from): FAL_KEY env var, else a `.env` in cwd, extra_dirs, ~/.config/falg."""
    if os.environ.get("FAL_KEY"):
        return os.environ["FAL_KEY"], "FAL_KEY environment variable"
    for d in [Path.cwd(), *extra_dirs, CONFIG_DIR]:
        env = Path(d) / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                name, _, value = line.strip().partition("=")
                if name.strip().removeprefix("export ").strip() == "FAL_KEY" and value.strip():
                    return value.strip().strip("'\""), str(env)
    return None, None


def find_key(extra_dirs: Iterable[Path] = ()) -> str | None:
    return find_key_source(extra_dirs)[0]


def save_key(key: str | None) -> Path:
    """Write (or with None, remove) FAL_KEY in ~/.config/falg/.env, keeping other lines; mode 600."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.chmod(0o700)
    env = CONFIG_DIR / ".env"
    lines = [ln for ln in (env.read_text(encoding="utf-8").splitlines() if env.is_file() else [])
             if ln.strip().partition("=")[0].removeprefix("export ").strip() != "FAL_KEY"]
    if key:
        lines.append(f"FAL_KEY={key}")
    env.touch(mode=0o600)
    env.chmod(0o600)
    env.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return env


def mask(key: str) -> str:
    return key[:4] + "…" + key[-4:] if len(key) > 12 else "****"


# OSError covers URLError, TimeoutError, ConnectionError and ssl.SSLError
NETWORK_ERRORS = (OSError, http.client.HTTPException)


def http_json(url: str, key: str | None = None, payload: dict | None = None,
              timeout: int = 60, retries: int = 3, abort: threading.Event | None = None) -> dict:
    """abort: checked before every attempt and during retry waits; raises Cancelled when set,
    so a request that hasn't been sent yet (e.g. backing off after a 429) is never sent."""
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {**UA, "Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Key {key}"

    def pause(seconds: float) -> None:
        if abort is None:
            time.sleep(seconds)
        elif abort.wait(seconds):
            raise Cancelled("cancelled before submission")

    for attempt in range(retries + 1):
        if abort is not None and abort.is_set():
            raise Cancelled("cancelled before submission")
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:1200]
            e.close()
            # retry rate limits always: a 429 means the request was rejected, so even a POST can't
            # submit a paid job twice. Retry server errors on GETs only (the POST may have landed).
            if (e.code == 429 or (data is None and e.code >= 500)) and attempt < retries:
                wait = e.headers.get("Retry-After") if e.code == 429 else None
                pause(min(float(wait), 60) if wait and wait.isdigit() else 3 * (attempt + 1))
                continue
            raise FalError(f"HTTP {e.code} from {url}: {body}") from None
        except NETWORK_ERRORS as e:
            # URLError, timeouts, and errors while reading the body (connection reset,
            # RemoteDisconnected, IncompleteRead, SSL), which urllib does not wrap
            if data is None and attempt < retries:
                pause(2 * (attempt + 1))
                continue
            raise FalError(f"{type(e).__name__} for {url}: {e}") from None
    raise AssertionError("unreachable")


_submitted = 0  # queue submissions accepted by fal in this process (each one is billed)
_submitted_lock = threading.Lock()


def submitted_count() -> int:
    return _submitted


def reset_submitted() -> None:
    global _submitted
    with _submitted_lock:
        _submitted = 0


class FalError(RuntimeError):
    pass


class Cancelled(FalError):
    pass


def run(endpoint: str, args: dict, key: str, *, poll: float = 2.0, max_wait: int = 900,
        on_submit: Callable[[dict], None] | None = None,
        cancel: threading.Event | None = None,
        no_submit: threading.Event | None = None) -> tuple[str | None, dict]:
    """Submit to the queue, wait, return (request_id, result). Always uses the returned URLs.

    on_submit gets the queue's submission info (request_id, status_url, response_url) as soon
    as the job is accepted. Setting `no_submit` stops a job that hasn't been sent yet, including
    one waiting to retry. Setting `cancel` does that too, and also stops waiting at the next poll
    (a submitted job keeps running on fal and is still billed)."""
    if cancel is not None and cancel.is_set():
        raise Cancelled("cancelled before submission")
    # callers that pass both set no_submit whenever they set cancel
    sub = http_json(f"{QUEUE_BASE}/{endpoint}", key, args, abort=no_submit or cancel)
    global _submitted
    with _submitted_lock:
        _submitted += 1
    rid = sub.get("request_id")
    if on_submit:
        on_submit({k: sub.get(k) for k in ("request_id", "status_url", "response_url")})
    deadline = time.time() + max_wait
    while True:
        st = http_json(sub["status_url"], key)
        status = st.get("status")
        if status == "COMPLETED":
            if st.get("error"):
                raise FalError(f"{endpoint} failed: {st['error']}")
            break
        if status not in ("IN_QUEUE", "IN_PROGRESS", None):
            raise FalError(f"{endpoint}: unexpected status {json.dumps(st)[:400]}")
        if time.time() > deadline:
            raise FalError(f"timed out after {max_wait}s (request {rid})")
        if cancel is not None:
            if cancel.wait(poll):
                raise Cancelled(f"stopped waiting (request {rid} may still finish on fal)")
        else:
            time.sleep(poll)
    return rid, http_json(sub["response_url"], key)


def media_in(result) -> list[dict]:
    """Every file object ({url, content_type?, file_name?, width?, ...}) in a result, in order."""
    found: list[dict] = []

    def walk(x):
        if isinstance(x, dict):
            url = x.get("url")
            if isinstance(url, str) and url.startswith("http") and (
                    "content_type" in x or "file_name" in x or "width" in x):
                found.append(x)
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(result)
    return found


EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg",
       "image/gif": ".gif", "video/mp4": ".mp4", "audio/mpeg": ".mp3", "audio/wav": ".wav",
       "model/gltf-binary": ".glb"}


def ext_for(f: dict) -> str:
    suffix = Path(f.get("file_name") or "").suffix
    if suffix:
        return suffix.lower()
    return EXT.get(f.get("content_type") or "", "") or Path(f["url"].split("?")[0]).suffix or ".bin"


def sidecar_name(file_name: str) -> str:
    """`x.png` -> `x.json`; a downloaded `x.json` gets `x.sidecar.json` so it isn't overwritten."""
    p = Path(file_name)
    return p.stem + (".sidecar.json" if p.suffix.lower() == ".json" else ".json")


def download(url: str, path: Path, retries: int = 3) -> None:
    """GET a result file; retried, since by now the output is already paid for."""
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 429) or attempt == retries:
                raise FalError(f"HTTP {e.code} downloading {url}") from None
        except NETWORK_ERRORS as e:
            if attempt == retries:
                raise FalError(f"{type(e).__name__} downloading {url}: {e}") from None
        time.sleep(2 * (attempt + 1))
    path.write_bytes(data)


def as_url(src: str | Path) -> str:
    """URLs pass through; local files become data URIs."""
    s = str(src)
    if s.startswith(("http://", "https://", "data:")):
        return s
    p = Path(s).expanduser()
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def elide_data(x):
    """Copy of x with data URIs shortened (for logs and sidecars)."""
    if isinstance(x, str) and x.startswith("data:"):
        return x[:x.find(",") + 1] + f"...({len(x)} chars)"
    if isinstance(x, dict):
        return {k: elide_data(v) for k, v in x.items()}
    if isinstance(x, list):
        return [elide_data(v) for v in x]
    return x


# ---- catalog helpers (public endpoints, no key needed)

def search_models(query: str, limit: int = 30, category: str | None = None) -> list[dict]:
    from urllib.parse import urlencode
    params = {"q": query, "limit": limit}
    if category:
        params["category"] = category
    return http_json(f"https://api.fal.ai/v1/models?{urlencode(params)}").get("models", [])


def list_models(category: str | None = None, key: str | None = None, query: str | None = None) -> list[dict]:
    """The whole catalog (paginated); pass the key to avoid anonymous rate limits."""
    from urllib.parse import urlencode
    rows, cursor = [], None
    while True:
        params = {"limit": 100, **({"category": category} if category else {}),
                  **({"q": query} if query else {}), **({"cursor": cursor} if cursor else {})}
        d = http_json(f"https://api.fal.ai/v1/models?{urlencode(params)}", key, retries=6)
        rows += d.get("models", [])
        if not d.get("has_more") or not d.get("next_cursor"):
            return rows
        cursor = d["next_cursor"]
        time.sleep(0.4)


def prices(endpoints: list[str], key: str) -> dict[str, dict]:
    """endpoint -> {unit_price, unit, currency} from fal's pricing API (needs a key)."""
    from urllib.parse import urlencode
    out: dict[str, dict] = {}
    for i in range(0, len(endpoints), 40):
        q = urlencode([("endpoint_id", e) for e in endpoints[i:i + 40]])
        for p in http_json(f"https://api.fal.ai/v1/models/pricing?{q}", key, retries=6).get("prices", []):
            out[p["endpoint_id"]] = p
        time.sleep(0.4)
    return out


def input_schema(endpoint: str) -> dict:
    from urllib.parse import quote
    spec = http_json(f"https://fal.ai/api/openapi/queue/openapi.json?endpoint_id={quote(endpoint, safe='/')}")
    schemas = spec.get("components", {}).get("schemas", {})
    # the request body schema of the POST to the endpoint
    for path, ops in spec.get("paths", {}).items():
        post = ops.get("post") if isinstance(ops, dict) else None
        if not post or "requestBody" not in post:
            continue
        ref = (post["requestBody"].get("content", {}).get("application/json", {})
               .get("schema", {}).get("$ref", ""))
        if ref:
            return {"name": ref.rsplit("/", 1)[-1], "schema": schemas.get(ref.rsplit("/", 1)[-1], {}),
                    "all": schemas}
    for name, s in schemas.items():
        if name.endswith("Input"):
            return {"name": name, "schema": s, "all": schemas}
    raise FalError(f"no input schema found for {endpoint}")


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) from a PNG/JPEG/WebP header, without Pillow; None if unknown or truncated."""
    import struct
    try:
        return _image_size(path)
    except struct.error:  # header shorter than it claims
        return None


def _image_size(path: Path) -> tuple[int, int] | None:
    import struct
    with open(path, "rb") as fh:
        head = fh.read(64)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", head[16:24])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            kind = head[12:16]
            if kind == b"VP8X":
                return (int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1)
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", head[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L":
                b = int.from_bytes(head[21:25], "little")
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if head[:2] == b"\xff\xd8":
            fh.seek(2)
            while True:
                marker = fh.read(2)
                if len(marker) < 2 or marker[0] != 0xFF:
                    return None
                if marker[1] in (0xD8, 0x01) or 0xD0 <= marker[1] <= 0xD7:
                    continue
                (length,) = struct.unpack(">H", fh.read(2))
                if marker[1] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">xHH", fh.read(5))
                    return w, h
                fh.seek(length - 2, 1)
    return None
