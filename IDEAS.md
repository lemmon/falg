# Ideas

Planned or possible improvements. Some are inspired by [similar projects](README.md#similar-projects).

### MCP server mode (inspired by fal-cli)

Expose falg as an MCP server so AI assistants (Claude Code, Claude Desktop, Cursor) can call it as tools, not just shell commands.

- **Tools:** `run_config`, `generate`, `edit`, `cutout`, `list_models`, `catalog_status`, `schema`.
- **Return:** file paths and sidecar JSON, which the `--json` output already provides.
- **Cost guard:** keep it by requiring a `max_cost` argument on every paid tool.
- **Design:** a thin layer over `cli.py`'s functions, since the logic already lives in `plan.py` and `runner.py`.

### Cached live pricing (inspired by falcon)

Replace the hand-written `price` values in `models.json` with fal's pricing API (`fal.prices()`, already used by `falg catalog`).

- **Caching:** cache the results in `~/.config/falg/prices.json` for about 24 h.
- **Fallback:** use the registry estimate when the API fails or there is no key.
- **Caveat:** the API reports some models in generic `units` (e.g. GPT Image, Nano Banana: `$1 / units`), which isn't a per-image price. Use only `images` and `megapixels` units directly. Megapixels × the requested size gives a cost, as for FLUX 3 at $0.048/MP. Keep estimates for the rest.
- **Check:** compare against what fal actually charged for a few runs before trusting it.

### Smaller items

- **SVG output:** GPT Image 2.6 can return SVG (`output_format: svg`, `svg_model`). Worth trying for clean one-ink logos. `cutout` would need an SVG path, or fal could rasterise.
- **Large inputs:** upload big local images to fal storage instead of sending data URIs. Edits currently send them inline, which is about 1.6 MB for a typical PNG.
- **Nested `call` arguments:** support `image_size[width]:=1024`-style syntax like `fal api`. Today it needs `image_size:='{"width":1024,"height":1024}'`.
- **Gallery:** add a "pick" button that copies the chosen files into a `picks/` folder.
