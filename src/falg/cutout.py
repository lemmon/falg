"""Remove a plain white or black background and produce a print-ready PNG (e.g. for DTF).

--bg white (default): artwork drawn on WHITE. Everything (near-)white becomes transparent --
    outside AND inside the figure; the rest stays.
--bg black: artwork drawn in light inks on BLACK. Everything (near-)black becomes transparent.
    Implemented by inverting the image, running the same steps, and inverting the colours back.

Steps (the Photoshop "image as its own mask + Levels + Defringe" technique):
  1. Crop to the artwork (ignoring stray specks); with --fit W H (cm), resize (Lanczos) to the
     largest size that fits the box at --ppi.
  2. Density mask: d = 1 - darkest channel / 255. Paper = 0, solid ink = 1.
  3. Levels on the mask: d <= --low is transparent, d >= --high is fully opaque. Default is
     HARD alpha (0/255); a pixel is kept if it is at least half way. --soft keeps graded alpha.
  4. Defringe: edge pixels partly blended with the paper get their ink colour back, so lines
     get no light halo. Hard alpha: pixels near the cut edge take the colour of the densest
     ink next to them; solid areas, pale ones too, keep their colour. --soft: the white is
     un-blended ("colour to alpha"), which reproduces the original over white.
  5. Drop isolated specks < --min-speck px; optionally recolour everything to one --ink colour.
     Reports how much ink sits in marks thinner than --min-line-mm.
  6. Previews (unless --no-preview): the design on a fabric-like colour, plus a 100% detail crop
     on the OPPOSITE tone where any leftover fringe would be obvious.
Each output gets a .json sidecar with the source, settings and measurements.

Needs numpy, Pillow and scipy:  pip install 'falg[cutout]'
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageOps
    from scipy import ndimage
except ImportError as e:  # pragma: no cover
    raise SystemExit(f"cutout needs numpy, Pillow and scipy ({e.name} missing): "
                     "pip install 'falg[cutout]'") from None


def density(rgb: np.ndarray) -> np.ndarray:
    """0 = white paper, 1 = full ink. Same as using the inverted image as its own mask."""
    return 1.0 - rgb.min(axis=2).astype(np.float32) / 255.0


def levels(d: np.ndarray, low: float, high: float) -> np.ndarray:
    return np.clip((d - low) / (high - low), 0.0, 1.0)


def unblend_white(rgb: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Colour that, laid at coverage `a` over white, gives `rgb` (GIMP 'colour to alpha')."""
    a = np.maximum(a, 1e-3)[..., None]
    return np.clip(255.0 - (255.0 - rgb.astype(np.float32)) / a, 0, 255)


def densest_nearby(rgb: np.ndarray, d: np.ndarray, radius: int) -> np.ndarray:
    """For each pixel, the colour of the highest-density pixel within `radius` (a square)."""
    h, w = d.shape
    # one sortable key per pixel: density first, then the pixel's index to look its colour up
    key = np.round(d * 1023).astype(np.int64) * (h * w) + np.arange(h * w, dtype=np.int64).reshape(h, w)
    best = ndimage.maximum_filter(key, size=2 * radius + 1, mode="nearest") % (h * w)
    return rgb.reshape(-1, 3)[best.ravel()].reshape(h, w, 3)


def drop_specks(mask: np.ndarray, min_px: int) -> tuple[np.ndarray, int]:
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return mask, 0
    sizes = np.bincount(labels.ravel())
    small = sizes < min_px
    small[0] = False
    return mask & ~small[labels], int(small.sum())


def thin_share(mask: np.ndarray, min_mm: float, ppi: int) -> float:
    """% of kept pixels that belong to marks whose thickest point is below min_mm."""
    labels, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    # a line w px wide has max distance (w + 1) / 2, so this is exact for odd widths and errs
    # thin (towards a warning) by 1 px for even ones
    thick_px = 2 * ndimage.maximum(ndimage.distance_transform_edt(mask), labels, idx) - 1
    thick_mm = thick_px * 25.4 / ppi
    area = ndimage.sum(mask, labels, idx)
    return float(100 * area[thick_mm < min_mm].sum() / area.sum())


def hex_rgb(h: str) -> tuple[int, int, int]:
    s = h.removeprefix("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"--ink must be a hex colour like #FF2D95 or #F0F, got {h!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _flatten(im: Image.Image, bg: str) -> Image.Image:
    """RGB, with any transparency laid over the background colour being removed, so transparent
    pixels count as paper (a plain RGB conversion would turn them into their stored colour,
    usually black)."""
    if im.mode in ("RGBA", "LA", "PA", "La") or "transparency" in im.info:
        im = im.convert("RGBA")
        base = Image.new("RGBA", im.size, (255, 255, 255, 255) if bg == "white" else (0, 0, 0, 255))
        base.alpha_composite(im)
        im = base
    return im.convert("RGB")


def cutout(src: Path, out: Path, *, bg: str = "white", low: float = 0.10, high: float = 0.60,
           soft: bool = False, fit_cm: tuple[float, float] | None = None, ppi: int = 300,
           min_speck: int = 6, pad: int = 8, crop: bool = True, preview_dir: Path | None = None,
           ink: str | None = None, min_line_mm: float = 0.3) -> dict:
    if not 0 <= low < high <= 1:
        raise ValueError(f"need 0 <= --low < --high <= 1, got low {low}, high {high}")
    ink_rgb = hex_rgb(ink) if ink else None  # fail before any work
    with Image.open(src) as im:
        rgb = np.asarray(_flatten(ImageOps.exif_transpose(im), bg))  # phone photos and scans
    if bg == "black":
        rgb = 255 - rgb  # black paper -> white paper; light inks -> dark inks
    cut = (low + high) / 2

    # 1: crop to artwork (ignoring specks), optionally resize to fit the box at ppi
    if crop:
        # crop to what will survive: soft alpha keeps everything above `low`, hard keeps >= cut
        kept = density(rgb) > low if soft else density(rgb) >= cut
        mask, _ = drop_specks(kept, min_speck)  # same threshold as the output: never crop off kept marks
        ys, xs = np.nonzero(mask)
        if len(ys) == 0:
            raise ValueError(f"{src}: nothing left after removing the {bg} background")
        y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, rgb.shape[0])
        x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, rgb.shape[1])
        rgb = rgb[y0:y1, x0:x1]
    img0 = Image.fromarray(np.ascontiguousarray(rgb))
    scale = 1.0
    if fit_cm:
        box_px = [round(c / 2.54 * ppi) for c in fit_cm]
        scale = min(box_px[0] / img0.width, box_px[1] / img0.height)
    size = (round(img0.width * scale), round(img0.height * scale))
    big = np.asarray(img0.resize(size, Image.Resampling.LANCZOS) if scale != 1 else img0)

    # 2-3: density mask + levels
    d = density(big)
    a = levels(d, low, high)

    # 4: defringe -- edge pixels get their ink colour back; solid areas keep their colour
    if soft:
        colour, alpha = unblend_white(big, a), a   # exact: reproduces the original over white
    else:
        kept = a >= 0.5
        alpha = kept.astype(np.float32)
        # anti-aliasing blends ~1-2 source px with the paper, more after upscaling
        radius = max(2, int(np.ceil(2 * scale)))
        edge = kept & (ndimage.distance_transform_edt(kept) <= radius)
        colour = big.astype(np.float32)
        if edge.any():
            # not "colour to alpha" here: that assumes saturated ink and would turn a pale fill's
            # edge (or a whole pale area) dark; take the nearest solid ink's colour instead
            colour[edge] = densest_nearby(big, d, radius)[edge]

    # 5: specks, ink, write
    keep, specks = drop_specks(alpha > 0, min_speck)
    alpha = np.where(keep, alpha, 0.0)
    colour = colour.round().astype(np.uint8)
    if bg == "black":
        colour = 255 - colour  # back to the real (light) ink colours
    if ink:
        colour[:] = ink_rgb
    rgba = np.dstack([colour, (alpha * 255).round().astype(np.uint8)])
    rgba[alpha == 0, :3] = 0
    img = Image.fromarray(rgba, "RGBA")
    img.save(out, dpi=(ppi, ppi), optimize=True)

    # 6: previews
    previews = []
    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)
        fabric, opposite = (((196, 214, 230), (55, 65, 85)) if bg == "white"
                            else ((28, 30, 36), (200, 200, 200)))
        canvas = Image.new("RGBA", size, (*fabric, 255))
        canvas.alpha_composite(img)
        p1 = preview_dir / (out.stem + "__preview.jpg")
        canvas.convert("RGB").resize((max(size[0] // 2, 1), max(size[1] // 2, 1)),
                                     Image.Resampling.LANCZOS).save(p1, quality=88)
        cx, cy = size[0] // 2, int(size[1] * 0.35)
        detail = Image.new("RGBA", (700, 500), (*opposite, 255))
        detail.alpha_composite(img.crop((cx - 350, cy - 250, cx + 350, cy + 250)))
        p2 = preview_dir / (out.stem + "__detail-100pct.png")
        detail.convert("RGB").save(p2)
        previews = [p1, p2]

    return {
        "file": out.name, "previews": previews,
        "px": list(size),
        "cm": [round(size[0] / ppi * 2.54, 1), round(size[1] / ppi * 2.54, 1)],
        "ppi": ppi,
        "scale": round(scale, 3),
        "coverage_pct": round(100 * float((alpha > 0).mean()), 1),
        "specks_removed": specks,
        "thin_ink_pct": round(thin_share(alpha > 0, min_line_mm, ppi), 1),
        "hard_alpha": not soft,
    }


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:  # b doesn't exist (yet)
        return False


def run_cli(args) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    preview_dir = None if args.no_preview else args.out / "preview"
    names = args.names or [p.stem for p in args.inputs]
    if len(names) != len(args.inputs):
        raise SystemExit("--names needs one name per input")
    results = []
    protected = {Path(p).resolve() for p in args.inputs}  # never overwrite an input
    for src in args.inputs:
        protected.add(Path(src).with_suffix(".json").resolve())  # ...or its sidecar
    written: set[Path] = set()
    for src, name in zip(args.inputs, names):
        stem = f"{name}__{args.suffix}" if args.suffix else name
        if "/" in stem or "\\" in stem or stem.startswith("."):
            raise SystemExit(f"invalid output name {stem!r}")
        tmp = args.out / f".{stem}.partial-{os.getpid()}.png"  # renamed once the final name is known
        settings = dict(bg=args.bg, low=args.low, high=args.high, soft=args.soft,
                        fit_cm=tuple(args.fit) if args.fit else None, ppi=args.ppi,
                        min_speck=args.min_speck, pad=args.pad, crop=not args.no_crop,
                        ink=args.ink, min_line_mm=args.min_line_mm)
        try:
            r = cutout(src, tmp, preview_dir=preview_dir, **settings)
            # size in the name when fitting: name__WxHcm.png
            final = args.out / (f"{stem}__{r['cm'][0]:g}x{r['cm'][1]:g}cm.png" if args.fit else f"{stem}.png")
            side_path = final.with_suffix(".json")
            preview_moves = [(pv, pv.with_name(pv.name.replace(tmp.stem, final.stem, 1)))
                             for pv in r["previews"]]
            targets = {final.resolve(), side_path.resolve(), *(new.resolve() for _, new in preview_moves)}
            # compare names, and file identity: on case-insensitive filesystems (macOS, Windows)
            # logo.png and Logo.png are the same file
            clash = (targets & (protected | written)) | {
                t for t in targets if t.exists() and any(_same_file(t, p) for p in protected | written)}
            if clash:
                raise SystemExit(f"{src}: output {sorted(map(str, clash))[0]} would overwrite an input or "
                                 "another output; use --suffix, --names or another -o folder")
            tmp.replace(final)
        except BaseException:
            if preview_dir:  # drop previews of the abandoned temp output
                for pv in preview_dir.glob(tmp.stem + "__*"):
                    pv.unlink(missing_ok=True)
            raise
        finally:
            tmp.unlink(missing_ok=True)
        written |= targets
        for i, (pv, new) in enumerate(preview_moves):
            pv.replace(new)
            r["previews"][i] = new
        r["file"] = final.name
        r["previews"] = [str(p.relative_to(args.out)) for p in r["previews"]]
        side = {**r, "source": str(Path(src).resolve()),
                "created": datetime.now().isoformat(timespec="seconds"),
                "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in settings.items()}}
        src_side = Path(src).with_suffix(".json")  # carry generation info along if present
        if src_side.is_file():
            try:
                side["source_sidecar"] = json.loads(src_side.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        side_path.write_text(json.dumps(side, indent=2, ensure_ascii=False), encoding="utf-8")
        results.append(side)
        if not args.json:
            print(f"{r['file']}: {r['px'][0]}x{r['px'][1]} px = {r['cm'][0]}x{r['cm'][1]} cm "
                  f"@ {args.ppi} PPI, scale x{r['scale']}, coverage {r['coverage_pct']}%, "
                  f"specks removed {r['specks_removed']}, ink in marks <{args.min_line_mm} mm: "
                  f"{r['thin_ink_pct']}%")
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0
