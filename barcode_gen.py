"""
barcode_gen.py
--------------
Renders a barcode image for a user's barcode number, matching the look of a
printed student ID card: black bars over white, with the encoded digits
printed underneath in a monospace font (the same digits the bars encode).

Uses the `python-barcode` package (Code128) when it's installed, which
produces a real, scannable barcode. If that package isn't installed yet,
falls back to a deterministic pseudo-barcode that still *looks* right in
the UI (same digits, same layout) but isn't a real scannable encoding.

Install the real encoder with:
    pip install python-barcode

The rendering logic now lives on the `BarcodeGenerator` class. A shared
instance (`_generator`) is created at the bottom of this module and the
module-level `get_barcode_image()` / `barcode_path_for()` functions just
delegate to it, so existing call sites (`barcode_gen.get_barcode_image(n)`)
keep working unchanged.
"""

import os
import hashlib
from PIL import Image, ImageDraw, ImageFont

try:
    import barcode as _barcode_lib
    from barcode.writer import ImageWriter
    HAVE_BARCODE_LIB = True
except ImportError:
    HAVE_BARCODE_LIB = False


class BarcodeGenerator:
    """Generates and caches Code128 barcode images (or a visual stand-in)."""

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.barcodes_dir = os.path.join(self.assets_dir, "barcodes")
        os.makedirs(self.barcodes_dir, exist_ok=True)
        self.have_barcode_lib = HAVE_BARCODE_LIB

    # ---- helpers ---------------------------------------------------------
    def _font(self, size):
        for name in ("consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _digits_only(self, value):
        return "".join(ch for ch in str(value) if ch.isdigit())

    def barcode_path_for(self, number):
        digits = self._digits_only(number)
        return os.path.join(self.barcodes_dir, f"code_{digits}.png")

    # ---- public API -------------------------------------------------------
    def get_barcode_image(self, number, force=False):
        """Returns a filesystem path to a cached barcode PNG for this number,
        generating it first if needed. Returns None if `number` has no digits."""
        digits = self._digits_only(number)
        if not digits:
            return None
        path = self.barcode_path_for(digits)
        if not force and os.path.exists(path):
            return path

        if self.have_barcode_lib:
            try:
                self._render_real_barcode(digits, path)
                return path
            except Exception:
                pass  # fall through to the pseudo-barcode renderer below
        self._render_pseudo_barcode(digits, path)
        return path

    # ---- renderers ---------------------------------------------------------
    def _render_real_barcode(self, digits, path):
        code128 = _barcode_lib.get("code128", digits, writer=ImageWriter())
        target = path[:-4] if path.lower().endswith(".png") else path
        code128.save(target, options={
            "write_text": False,
            "quiet_zone": 2.0,
            "module_height": 11.0,
            "module_width": 0.28,
            "background": "white",
            "foreground": "black",
        })

    def _render_pseudo_barcode(self, digits, path):
        """Deterministic bar pattern derived from the digit string. Looks like a
        barcode but is only used as a visual stand-in when python-barcode isn't
        installed - it does not encode a real, scannable Code128 symbol."""
        width, height = 360, 110
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)

        seed = int(hashlib.md5(digits.encode()).hexdigest(), 16)
        x = 14
        bar_top, bar_bottom = 10, height - 32
        while x < width - 14:
            seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
            bar_w = 2 + (seed % 3)
            seed = (seed * 1103515245 + 12345) & 0xFFFFFFFF
            if seed % 5 != 0:
                draw.rectangle([x, bar_top, x + bar_w, bar_bottom], fill="black")
            x += bar_w + 1

        font = self._font(20)
        tb = draw.textbbox((0, 0), digits, font=font)
        tw = tb[2] - tb[0]
        draw.text(((width - tw) / 2, bar_bottom + 6), digits, font=font, fill="black")
        img.save(path, "PNG")


# --------------------------------------------------------------------------
# Shared instance + backward-compatible module-level functions, so existing
# call sites (`barcode_gen.get_barcode_image(n)`) keep working unchanged.
# --------------------------------------------------------------------------
_generator = BarcodeGenerator()

BARCODES_DIR = _generator.barcodes_dir
ASSETS_DIR = _generator.assets_dir


def barcode_path_for(number):
    return _generator.barcode_path_for(number)


def get_barcode_image(number, force=False):
    return _generator.get_barcode_image(number, force=force)
