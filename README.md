# falg

A small CLI for generating and editing images on [fal.ai](https://fal.ai). A JSON config sets
up a prompt template, its variables and the models. falg runs every combination in parallel
and downloads the results. Each output gets a `.json` sidecar describing how it was made, and
each run gets an HTML gallery for comparing the results side by side.

```sh
falg run examples/styles.json --only subject=fox --dry-run   # preview prompts and cost
falg run examples/styles.json --only subject=fox -y          # 2 styles x 3 models, in parallel
open examples/generations/*-styles/index.html                # compare the results
```

> **Unofficial.** falg is a community tool, not affiliated with or endorsed by fal.ai. It
> uses fal's public queue API with your own API key; generations are billed to your fal account.

## Why

falg started in a DTF (direct-to-film) T-shirt printing project. We needed many design
variations: several styles and models, compared side by side, then turned into
print-ready PNGs. Beyond that, the goal is to automate image generation for other projects
too. The same config can be rerun later, each image records how it was made, and scripts
or AI agents can drive it without prompts. `cutout` is the only print-specific part.

## Similar projects

Other tools take different approaches; one of them may suit you better:

- **[fal CLI](https://fal.ai/docs/api-reference/cli/api.md)** (official): `fal api` calls any
  endpoint from the terminal. It's mainly for deploying your own apps on fal.
- **[falcon](https://github.com/CoinAnole/falcon)**: a polished single-image workflow with a
  terminal UI, presets, upscaling and background removal.
- **[fal-cli](https://github.com/ilkerzg/fal-cli)**: batches and spending limits, and an MCP
  server for AI assistants.
- **[falgen](https://github.com/ilkerzg/falgen)**: a conversational tool that picks a model for
  you, covering images, video and audio.
- **[gen](https://github.com/cozy-creator/gen)**: a minimal Go CLI for generating and editing.
- **[llm-fal](https://pypi.org/project/llm-fal/)**: fal models inside Simon Willison's `llm`.

falg focuses on config-driven batches: prompt × model grids, a sidecar per output, and a
comparison gallery. Some of its planned ideas come from these projects (see [IDEAS.md](IDEAS.md)).

## Install

Requires Python 3.10+.

```sh
pipx install 'git+https://github.com/lemmon/falg.git#egg=falg[cutout]'
# or: uv tool install 'falg[cutout] @ git+https://github.com/lemmon/falg.git'
```

The fal part is standard library only. The optional `[cutout]` extra adds numpy, Pillow and
SciPy for `falg cutout`; leave it out if you only generate.

For development:

```sh
git clone https://github.com/lemmon/falg.git && cd falg
python3 -m venv .venv && .venv/bin/pip install -e '.[cutout]'
ln -sf "$PWD/.venv/bin/falg" ~/.local/bin/falg    # optional: put the command on PATH
.venv/bin/python -m unittest discover -s tests     # run the tests (no network, no spending)
```

**API key:** save it once for all projects:

```sh
falg auth            # asks for the key with hidden input; keeps it out of shell history
falg auth fal_xxx    # or pass it directly (it lands in shell history)
pbpaste | falg auth -   # or from stdin / the clipboard
falg auth --status   # which key is active here, and from where (masked)
falg auth --remove
```

The key is stored in `~/.config/falg/.env` with mode 600. falg uses the first key it finds:

1. `FAL_KEY` in the environment.
2. `FAL_KEY=...` in a `.env` in the current directory.
3. A `.env` in the config file's directory.
4. The global `~/.config/falg/.env`.

So a project can still use its own key.

## Commands

```sh
falg run job.json [--only axis=a,b] [--set var=text] [-m models] [-n 2] [-a 3:2] [--dry-run] [-y]
falg gen "a prompt" [-m nano-banana-2.1 gpt-image-2.5] [-n 2] [-a 3:2] [-p seed:=7 quality=low]
falg edit photo.png "make the cat smile" [-m nano-banana-2.1] [-i extra-ref.png]
falg call any/fal/endpoint prompt="..." num_images:=2 [--args body.json] [--file image_url=a.png]
falg auth              # save the API key globally (see Install)
falg models            # the registry: names, endpoints, price estimates (* = default)
falg catalog           # refresh MODELS.md: dated list of recent models + upgrade check
falg search "flux"     # fal's catalog: endpoint ids, category, release date
falg schema google/nano-banana-2.1      # an endpoint's input parameters, types, defaults
falg cutout art.png -o prints/ [--bg black] [--fit 21 14] [--ink "#FF2D95"]
```

Options shared by `run`, `gen` and `edit`:

- `--dry-run` prints the prompts and cost and sends nothing. With `--json` it prints the plan as JSON: prompts, request count, estimated cost and an example request.
- By default falg asks before spending; without a terminal it refuses. `-y` approves any cost. `--max-cost 2` approves runs estimated up to $2 and aborts above that, which suits scripts and agents. A model without a `price` can't be checked against a budget, so `--max-cost` refuses it; use `-y` to run it anyway.
- When `n` takes several requests (models without `batch`, or more than `max_batch` images), a fixed `seed` in `params` is offset per request by the number of images before it (seed 7 with `-n 3` on a single-image model gives 7, 8, 9; with batches of 4 it gives 7, 11), so you don't pay for the same image twice. The sidecars record the seed that was sent.
- Ctrl+C sends nothing more: queued jobs are cancelled, and so are jobs waiting to retry after a rate limit. It waits for the requests already sent, which fal has already billed. A second Ctrl+C stops waiting. Every request ID is recorded in `run.json` at submission, so results can still be recovered.
- `--json` prints the output files and sidecars as JSON, for scripts and agents. Progress goes to stderr.
- The exit code is 0 only if every request succeeded. If any failed it is 1, and `--json` reports how many under `failed`.
- `-o DIR` sets the parent output folder. The default is `generations/` next to the config, or in the current directory for `gen`.

`call` passes values like `fal api` does: `k=v` sends a string and `k:=json` sends a number, bool, list or object, e.g. `image_size:='{"width":1024,"height":1024}'`. `--file KEY=PATH` sends a local file as a data URI; repeat it for several files. `call` sends no cost question because the endpoint may not be in the registry.

## Output

```
generations/20261105-120000-chest-logos/
  sloth-firefighter__riso__gpt-image-2.5__01.png
  sloth-firefighter__riso__gpt-image-2.5__01.json   <- sidecar
  run.json      config snapshot + every request (ids, args, errors)
  index.html    grid: prompts (rows) x models (columns); toggle grey/white/black background
```

Files are named `<axis option names>__<model>__<nn>`.

Each sidecar holds:

- `file` and `created`;
- `seconds`, the request time;
- `model`, `mode` (generate or edit) and `endpoint`;
- `vars` (axis → option) and the final `prompt`;
- `sources`, the input images for edits;
- `seed` and `request_id`;
- `width`, `height`, `content_type` and `url` (fal CDN);
- `price_estimate`;
- the exact `args` sent (data URIs elided);
- the rest of the model `response`;
- `run` and `config`.

`cutout` writes its own sidecar with the measurements and settings. If the source image has a falg sidecar, cutout embeds it as `source_sidecar`, so a print file keeps its prompt history.

## Job config

```json
{
  "name": "chest-logos",
  "models": ["gpt-image-2.5", "nano-banana-2.1"],
  "n": 1,
  "aspect": "1:1",
  "template": ["{subject}. Style: {style}", "{background} {rules}"],
  "vars": {
    "subject": { "fox": "A cheerful red fox", "owl": "A tiny owl astronaut" },
    "style": {
      "riso": "Retro risograph print, coarse halftone dots.",
      "ink": {
        "text": "Bold ink line art.",
        "set": { "background": "On pure black." }
      }
    },
    "background": "On a plain pure white background.",
    "rules": ["No text.", "No frame, no border."]
  },
  "params": {
    "*": { "output_format": "png" },
    "gpt-image-2.5": { "quality": "medium" }
  },
  "model_defs": {},
  "images": [],
  "out": "generations",
  "gallery_background": "#888"
}
```

**`vars`** builds the prompt from the template:

- A **string** is a constant. A **list** of strings is a constant too, joined with spaces, so long text stays readable.
- An **object** is an **axis** of named options. Every combination of axes becomes one prompt; the example above gives 2 subjects × 2 styles = 4 prompts.
- An option can be `{"text": ..., "set": {var: value}}`. That overrides other variables for that option only, as `ink` does for the background above.
- `{var}` works inside variables too, nested. An unresolved `{name}` (usually a typo) stops the run before anything is sent; `--dry-run` shows it. A plain `prompt` with no `vars` or `template` may contain braces.
- Use `--only style=riso` to pick a subset, and `--set background="..."` to override a constant (or `--set prompt="..."` for a single-prompt config). `--set` stops with an error for an unknown name or an axis, rather than running without the override.

**Other fields:**

- **`prompt` / `prompts`:** shortcuts with no template. `prompts` can be a list or a `{name: text}` object.
- **`template`:** a string, or a list of strings joined with spaces. Default: `{prompt}`.
- **`aspect`:** each model gets it in its own form (see the registry below).
- **`params`:** raw request arguments merged last. `*` applies to every model; a model name applies to that model only.
- **`images`:** input images, as paths relative to the config, URLs, or data URIs. Any config with `images` uses the models' **edit** endpoints.
- **`model_defs`:** add or override models for this config only.

Fields starting with `_` are ignored at any level (top level, `vars`, axis options, `prompts`, `params`), so you can leave notes in `"_about"`. See `examples/`.

## Which models exist right now: MODELS.md

**`MODELS.md`** is a dated snapshot of fal's catalog. It lists the text-to-image and image-to-image models released in the last 180 days, newest first, with prices from fal's pricing API. Its "Registry check" table flags newer releases in the same family as each registry model. (On 2026-11-05 it caught GPT Image 2.6, released the day before.)

```sh
falg catalog                      # refresh MODELS.md (uses your key; takes ~10 s)
falg catalog --days 60 --categories text-to-image text-to-video image-to-video
```

Model names go stale fast, so check the file's date before choosing a model, and refresh it
if it is over 30 days old. `falg models` prints how old the snapshot is. `AGENTS.md` (also
linked as `CLAUDE.md`) tells AI assistants the same.

## Model registry

`src/falg/models.json` gives each model a `generate` and/or `edit` spec:

- `endpoint` and `price`: USD per image, a rough guess. Many endpoints bill per megapixel, resolution or quality; the estimate is only meant to flag a run that costs much more than you expected;
- `default`, which puts the model in the default set when `-m` and `models` are not given;
- `batch`, which sends one request with `num_images` instead of n separate requests;
- `max_batch`, the endpoint's `num_images` maximum (see `falg schema`). A larger n is split into
  several requests. Without it, falg assumes 4;
- `params`, the default request arguments. Overrides merge key by key, so `"params": {"seed": 7}` keeps the built-in params; set a key to `null` to remove it (this works in a config's `params` and in `-p key:=null` too);
- `size`, how the aspect ratio is sent:
  - `px`: `image_size {width, height}`, computed from the aspect and `pixels`, rounded to a multiple of 16. For edits with aspect `auto`, the aspect comes from the first input image (a local file); for a URL, falg leaves the size to the endpoint.
  - `aspect`: an `aspect_ratio` string.
  - `enum`: a size from `enum_map`, keyed by aspect: a preset name, or `{width, height}` for endpoints that accept only listed sizes. Other aspects are an error before anything is sent.
  - `none`: no size argument.

To add a new model, check its inputs with `falg schema <endpoint>`. Then add it to `~/.config/falg/models.json` (merged over the built-ins), or to a config's `model_defs`:

```json
{
  "my-model": {
    "note": "...",
    "generate": {
      "endpoint": "vendor/model/text-to-image",
      "price": 0.04,
      "size": "aspect",
      "batch": true,
      "max_batch": 4,
      "params": { "output_format": "png" }
    }
  }
}
```

## cutout

This removes a plain **white** background (art drawn on white) or a **black** one (light art on black) and writes a print-ready PNG. It is the Photoshop "image as its own mask + Levels" technique, plus a defringe step:

- **Alpha:** hard by default, 0 or 255 only.
- **Defringe:** pixels along the cut edge take the colour of the ink next to them, so lines get no light halo. Solid areas keep their colour, pale ones too.
- **Size:** crops to the artwork. Optionally fits it into `--fit W H` cm at `--ppi`, and adds the size to the file name.
- **One ink:** `--ink "#RRGGBB"` makes everything that prints a single colour.
- **Checks:** reports coverage and how much ink sits in marks thinner than `--min-line-mm`.
- **Previews:** the design on a fabric colour, plus a 100% detail crop on the opposite tone, where any fringe shows. `--no-preview` skips them.

Run `falg cutout -h` for the full explanation and tuning flags (`--low`, `--high`, `--soft`, `--min-speck`).

## Prompting tips

What has worked in practice, especially for artwork meant for print or cutouts:

- Generate on plain white or black and remove the background afterwards (`falg cutout`). Don't ask the generator for transparency.
- Ask for the subject to fill about 90% of the frame. For scenes, ask for a free-standing vignette with no background.
- Don't mention the end product (e.g. "T-shirt", "sticker") in prompts, or some models draw a mockup of it.
- For expression edits, describe the whole new expression ("calm, content, gently smiling, relaxed half-closed eyes"), not just "make it smile". FLUX edits sometimes drop characters; Nano Banana keeps scenes intact best.
