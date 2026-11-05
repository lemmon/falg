"""cutout tests (skipped without numpy/Pillow/scipy)."""

import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw

    from falg.cutout import cutout
except (ImportError, SystemExit):  # pragma: no cover
    cutout = None


@unittest.skipIf(cutout is None, "needs falg[cutout]")
class TestCutout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def draw(self, fill, bg="white"):
        im = Image.new("RGB", (400, 300), bg)
        ImageDraw.Draw(im).ellipse((100, 50, 300, 250), fill=fill)
        path = self.d / "in.png"
        im.save(path)
        return path

    def test_hard_alpha_crop_and_fit(self):
        r = cutout(self.draw((20, 20, 20)), self.d / "out.png", fit_cm=(2.0, 2.0), ppi=300)
        a = np.asarray(Image.open(self.d / "out.png"))[..., 3]
        self.assertTrue(set(np.unique(a)) <= {0, 255})
        self.assertEqual(max(r["px"]), round(2.0 / 2.54 * 300))
        self.assertEqual(Image.open(self.d / "out.png").info.get("dpi", (0, 0))[0].__round__(), 300)

    def test_solid_pale_fills_keep_their_colour(self):
        for fill in ((255, 150, 150), (140, 140, 140)):  # density between the cut and --high
            with self.subTest(fill=fill):
                cutout(self.draw(fill), self.d / "out.png")
                px = np.asarray(Image.open(self.d / "out.png"))
                centre = px[px.shape[0] // 2, px.shape[1] // 2]
                self.assertEqual((tuple(centre[:3]), centre[3]), (fill, 255))

    def test_dark_edges_get_no_light_fringe(self):
        im = Image.new("RGB", (400, 300), "white")
        ImageDraw.Draw(im).ellipse((100, 50, 300, 250), fill=(20, 20, 20))
        im = im.resize((1600, 1200), Image.Resampling.LANCZOS).resize((400, 300), Image.Resampling.LANCZOS)
        im.save(self.d / "aa.png")  # anti-aliased edge
        cutout(self.d / "aa.png", self.d / "out.png")
        px = np.asarray(Image.open(self.d / "out.png"))
        self.assertLess(px[px[..., 3] == 255][:, :3].max(), 60)

    def test_ink_short_hex_and_bad_values(self):
        cutout(self.draw((0, 0, 0)), self.d / "out.png", ink="#F0F")
        px = np.asarray(Image.open(self.d / "out.png"))
        self.assertEqual({tuple(c) for c in px[px[..., 3] == 255][:, :3]}, {(255, 0, 255)})
        for bad in ("red", "#12345", "#GGGGGG"):
            with self.subTest(ink=bad), self.assertRaises(ValueError):
                cutout(self.draw((0, 0, 0)), self.d / "bad.png", ink=bad)
        self.assertFalse((self.d / "bad.png").exists())

    def test_thin_line_report_measures_odd_widths_exactly(self):
        from falg.cutout import thin_share
        mask = np.zeros((40, 40), bool)
        mask[5:35, 10:13] = True  # 3 px = 0.254 mm at 300 PPI
        self.assertEqual(thin_share(mask, 0.3, 300), 100.0)
        self.assertEqual(thin_share(mask, 0.25, 300), 0.0)

    def test_levels_must_be_ordered(self):
        for low, high in ((0.6, 0.4), (0.5, 0.5), (-0.1, 0.6), (0.1, 1.5)):
            with self.subTest(low=low, high=high), self.assertRaises(ValueError):
                cutout(self.draw((20, 20, 20)), self.d / "out.png", low=low, high=high)

    def test_black_background_keeps_light_ink(self):
        cutout(self.draw((250, 250, 250), bg="black"), self.d / "out.png", bg="black")
        px = np.asarray(Image.open(self.d / "out.png"))
        opaque = px[px[..., 3] == 255]
        self.assertTrue(len(opaque) and opaque[:, :3].min() > 200)

    def test_ink_recolour(self):
        cutout(self.draw((0, 0, 0)), self.d / "out.png", ink="#FF2D95")
        px = np.asarray(Image.open(self.d / "out.png"))
        self.assertEqual({tuple(c) for c in px[px[..., 3] == 255][:, :3]}, {(255, 45, 149)})

    def test_soft_mode_keeps_pale_artwork(self):
        src = self.draw((204, 204, 204))   # density 0.2: below the hard cut, above `low`
        with self.assertRaises(ValueError):
            cutout(src, self.d / "hard.png")
        r = cutout(src, self.d / "soft.png", soft=True)
        self.assertGreater(r["coverage_pct"], 50)


    def test_transparent_input_counts_as_background(self):
        for bg, ink in (("white", (20, 20, 20, 255)), ("black", (250, 250, 250, 255))):
            with self.subTest(bg=bg):
                im = Image.new("RGBA", (400, 300), (0, 0, 0, 0))  # transparent, stored as black
                ImageDraw.Draw(im).ellipse((100, 50, 300, 250), fill=ink)
                im.save(self.d / "rgba.png")
                r = cutout(self.d / "rgba.png", self.d / "out.png", bg=bg, crop=False)
                self.assertAlmostEqual(r["coverage_pct"], 100 * 3.1416 * 100 * 100 / (400 * 300), delta=2)

    def test_crop_keeps_small_marks_the_output_keeps(self):
        im = Image.new("RGB", (400, 300), "white")
        draw = ImageDraw.Draw(im)
        draw.rectangle((100, 100, 200, 200), fill="black")
        draw.rectangle((350, 20, 352, 22), fill="black")  # a 9 px dot, kept at --min-speck 6
        im.save(self.d / "dot.png")
        r = cutout(self.d / "dot.png", self.d / "out.png", pad=0)
        self.assertEqual(r["px"], [253, 181])  # x 100..352, y 20..200
        halftone = Image.new("RGB", (200, 200), "white")
        for x in range(10, 190, 10):
            for y in range(10, 190, 10):
                ImageDraw.Draw(halftone).rectangle((x, y, x + 3, y + 3), fill="black")
        halftone.save(self.d / "halftone.png")
        cutout(self.d / "halftone.png", self.d / "out.png", min_speck=0)  # no "nothing left"

    def test_exif_orientation_is_applied(self):
        im = Image.new("RGB", (400, 300), "white")
        ImageDraw.Draw(im).rectangle((20, 20, 380, 280), fill=(20, 20, 20))
        exif = Image.Exif()
        exif[0x0112] = 6  # displayed rotated by 90 degrees, as phones save photos
        im.save(self.d / "photo.jpg", exif=exif)
        r = cutout(self.d / "photo.jpg", self.d / "out.png", crop=False)
        self.assertEqual(r["px"], [300, 400])

    def run_cli(self, *argv):
        from falg.cli import build_parser
        args = build_parser().parse_args(["cutout", *argv])
        return args.func(args)

    def test_output_next_to_source_never_overwrites_it(self):
        src = self.draw((20, 20, 20))
        before = src.read_bytes()
        self.run_cli(str(src), "-o", str(self.d), "--fit", "2", "2", "--no-preview")
        self.assertEqual(src.read_bytes(), before)
        self.assertTrue(list(self.d.glob("in__*cm.png")))
        with self.assertRaises(SystemExit):  # without --fit the output name would be in.png
            self.run_cli(str(src), "-o", str(self.d))
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(list(self.d.glob(".*partial*")) + list(self.d.glob("preview/.*")), [])

    def test_previews_never_overwrite_an_input(self):
        a = self.draw((20, 20, 20))
        out = self.d / "out"
        (out / "preview").mkdir(parents=True)
        victim = out / "preview" / "in__preview.jpg"   # where in.png's preview would land
        victim.write_bytes(b"not an image, but an input")
        with self.assertRaises(SystemExit):
            self.run_cli(str(a), str(victim), "-o", str(out))
        self.assertEqual(victim.read_bytes(), b"not an image, but an input")

    def test_input_is_protected_on_case_insensitive_filesystems(self):
        src = self.draw((20, 20, 20))
        upper = src.with_name("Logo.png")
        src.rename(upper)
        if not (self.d / "logo.png").exists():
            self.skipTest("case-sensitive filesystem")
        before = upper.read_bytes()
        with self.assertRaises(SystemExit):  # logo.png is Logo.png here
            self.run_cli(str(upper), "--names", "logo", "-o", str(self.d), "--no-preview")
        self.assertEqual(upper.read_bytes(), before)

    def test_two_inputs_with_the_same_name_are_rejected(self):
        a = self.draw((20, 20, 20))
        (self.d / "b").mkdir()
        b = self.d / "b" / "in.png"
        b.write_bytes(a.read_bytes())
        with self.assertRaises(SystemExit):
            self.run_cli(str(a), str(b), "-o", str(self.d / "out"), "--no-preview")


if __name__ == "__main__":
    unittest.main()
