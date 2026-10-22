"""
assets.py
---------
Generates polished, illustrated "photo card" images for facilities so the
GUI has something nicer to show than plain text rows. There are no real
facility photographs in this project, so each card is procedurally drawn
with PIL: a soft gradient background colour-coded by category, a simple
line-art icon representing the facility type, and a legible text overlay
with the facility's name, type, location and condition badge.

Generated images are cached on disk under ASSETS_DIR / "cards" and are
regenerated only when the facility's own data changes (name / condition /
location / capacity), so the app stays fast even with many facilities.

All of the drawing logic now lives on the `FacilityCardRenderer` class. A
single shared instance (`_renderer`) is created at the bottom of this
module and the module-level `get_facility_card()` / `get_placeholder_card()`
/ `card_path_for()` functions just delegate to it, so existing call sites
elsewhere in the app (`assets.get_facility_card(f)`) keep working unchanged.
"""

import os
import math
import hashlib
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


class FacilityCardRenderer:
    """Renders and caches procedurally-drawn facility 'photo cards'."""

    CARD_SIZE = (760, 380)  # 2:1 wide card used in the carousel

    # ---- palette ----------------------------------------------------
    CATEGORY_COLORS = {
        "Room":      ((66, 99, 235), (110, 150, 255)),
        "Sports":    ((15, 148, 120), (52, 199, 165)),
        "Equipment": ((235, 124, 32), (255, 170, 76)),
    }
    DEFAULT_GRADIENT = ((90, 96, 110), (140, 146, 160))

    CONDITION_COLORS = {
        "Good": (34, 160, 90),
        "Fair": (214, 152, 20),
        "Under Maintenance": (196, 76, 36),
        "Out of Service": (150, 40, 40),
    }

    ICON_WHITE = (255, 255, 255, 235)
    ICON_WHITE_SOFT = (255, 255, 255, 90)

    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.cards_dir = os.path.join(self.assets_dir, "cards")
        self.uploads_dir = os.path.join(self.assets_dir, "facility_uploads")
        os.makedirs(self.cards_dir, exist_ok=True)
        os.makedirs(self.uploads_dir, exist_ok=True)

        # Dispatch table built here (rather than at class-definition time)
        # so it can bind to `self` and reach instance state if ever needed.
        self._icon_by_type = {
            "Lecture Hall": self._icon_lecture_hall,
            "Classroom": self._icon_lecture_hall,
            "Lab": self._icon_lab,
            "Gym": self._icon_gym,
            "Court": self._icon_court,
            "Pool": self._icon_pool,
            "Field": self._icon_field,
            "Projector": self._icon_projector,
            "Laptop": self._icon_laptop,
            "Lab Instrument": self._icon_instrument,
        }

    # ---- font helper --------------------------------------------------
    def _font(self, size, bold=False):
        candidates = (
            ["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf"] if bold
            else ["segoeui.ttf", "arial.ttf"]
        )
        for name in candidates:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    # ---- gradient background ------------------------------------------
    def _gradient(self, size, top_color, bottom_color):
        w, h = size
        top = Image.new("RGB", size, top_color)
        bottom = Image.new("RGB", size, bottom_color)
        mask = Image.new("L", size)
        mask_data = []
        for y in range(h):
            mask_data.extend([int(255 * (y / max(h - 1, 1)))] * w)
        mask.putdata(mask_data)
        return Image.composite(bottom, top, mask)

    def _soft_circles(self, draw, w, h, seed):
        """Decorative translucent bokeh circles for visual depth."""
        rnd = (seed * 2654435761) & 0xFFFFFFFF
        for i in range(5):
            rnd = (rnd * 1103515245 + 12345) & 0xFFFFFFFF
            cx = int((rnd % 1000) / 1000 * w)
            rnd = (rnd * 1103515245 + 12345) & 0xFFFFFFFF
            cy = int((rnd % 1000) / 1000 * h * 0.6)
            rnd = (rnd * 1103515245 + 12345) & 0xFFFFFFFF
            r = 30 + int((rnd % 1000) / 1000 * 90)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 18))

    # ---- per-type icon drawing -----------------------------------------
    def _icon_lecture_hall(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        draw.rounded_rectangle([x0, y0, x1, y0 + h * 0.22], radius=6,
                                outline=self.ICON_WHITE, width=4)
        rows, cols = 3, 4
        pad = w * 0.06
        cell_w = (w - pad * 2) / cols
        cell_h = h * 0.5 / rows
        top = y0 + h * 0.38
        for r in range(rows):
            for c in range(cols):
                cx0 = x0 + pad + c * cell_w + cell_w * 0.12
                cy0 = top + r * cell_h
                cx1 = cx0 + cell_w * 0.76
                cy1 = cy0 + cell_h * 0.62
                draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=3,
                                        outline=self.ICON_WHITE, width=3)

    def _icon_lab(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        neck_w = w * 0.14
        cx = (x0 + x1) / 2
        draw.line([cx - neck_w / 2, y0, cx - neck_w / 2, y0 + h * 0.35],
                   fill=self.ICON_WHITE, width=4)
        draw.line([cx + neck_w / 2, y0, cx + neck_w / 2, y0 + h * 0.35],
                   fill=self.ICON_WHITE, width=4)
        flask = [
            (cx - neck_w / 2, y0 + h * 0.35),
            (x0, y1),
            (x1, y1),
            (cx + neck_w / 2, y0 + h * 0.35),
        ]
        draw.line(flask + [flask[0]], fill=self.ICON_WHITE, width=4, joint="curve")
        liquid_y = y0 + h * 0.68
        draw.polygon([
            (x0 + w * 0.12, liquid_y), (x1 - w * 0.12, liquid_y),
            (x1 - w * 0.02, y1 - h * 0.04), (x0 + w * 0.02, y1 - h * 0.04)
        ], fill=(255, 255, 255, 70))
        for bx, by in [(0.32, 0.5), (0.5, 0.35), (0.66, 0.55)]:
            r = 4
            px, py = x0 + w * bx, y0 + h * by
            draw.ellipse([px - r, py - r, px + r, py + r], fill=self.ICON_WHITE)

    def _icon_gym(self, draw, box):
        x0, y0, x1, y1 = box
        cy = (y0 + y1) / 2
        bar_left, bar_right = x0 + (x1 - x0) * 0.18, x1 - (x1 - x0) * 0.18
        draw.line([bar_left, cy, bar_right, cy], fill=self.ICON_WHITE, width=6)
        for cx in (x0 + (x1 - x0) * 0.14, x1 - (x1 - x0) * 0.14):
            r = (y1 - y0) * 0.28
            draw.ellipse([cx - r * 0.35, cy - r, cx + r * 0.35, cy + r],
                          outline=self.ICON_WHITE, width=5)

    def _icon_court(self, draw, box):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=8, outline=self.ICON_WHITE, width=4)
        cx = (x0 + x1) / 2
        draw.line([cx, y0, cx, y1], fill=self.ICON_WHITE, width=3)
        r = min(x1 - x0, y1 - y0) * 0.16
        cy = (y0 + y1) / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=self.ICON_WHITE, width=3)

    def _icon_pool(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        for i, yfrac in enumerate((0.35, 0.55, 0.75)):
            y = y0 + h * yfrac
            points = []
            steps = 24
            for s in range(steps + 1):
                xx = x0 + w * s / steps
                yy = y + math.sin(s / steps * math.pi * 2.4 + i) * (h * 0.03)
                points.append((xx, yy))
            draw.line(points, fill=self.ICON_WHITE, width=4, joint="curve")

    def _icon_field(self, draw, box):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=8, outline=self.ICON_WHITE, width=4)
        cx = (x0 + x1) / 2
        draw.line([cx, y0, cx, y1], fill=self.ICON_WHITE, width=3)
        r = min(x1 - x0, y1 - y0) * 0.18
        cy = (y0 + y1) / 2
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=self.ICON_WHITE, width=3)
        boxw = (x1 - x0) * 0.16
        boxh = (y1 - y0) * 0.4
        draw.rectangle([x0, cy - boxh / 2, x0 + boxw, cy + boxh / 2],
                        outline=self.ICON_WHITE, width=3)
        draw.rectangle([x1 - boxw, cy - boxh / 2, x1, cy + boxh / 2],
                        outline=self.ICON_WHITE, width=3)

    def _icon_projector(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        body_top = y0 + h * 0.35
        draw.rounded_rectangle([x0, body_top, x1, y1], radius=8,
                                outline=self.ICON_WHITE, width=4)
        lens_cx, lens_cy = x0 + w * 0.28, (body_top + y1) / 2
        r = h * 0.14
        draw.ellipse([lens_cx - r, lens_cy - r, lens_cx + r, lens_cy + r],
                      outline=self.ICON_WHITE, width=4)
        beam = [
            (x0 + w * 0.5, body_top - h * 0.02),
            (x1, y0),
            (x1, body_top),
        ]
        draw.polygon(beam, fill=(255, 255, 255, 55))

    def _icon_laptop(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        screen_bottom = y0 + h * 0.62
        draw.rounded_rectangle([x0 + w * 0.12, y0, x1 - w * 0.12, screen_bottom],
                                radius=6, outline=self.ICON_WHITE, width=4)
        draw.polygon([
            (x0, y1), (x1, y1), (x1 - w * 0.06, screen_bottom), (x0 + w * 0.06, screen_bottom)
        ], outline=self.ICON_WHITE, width=4)

    def _icon_instrument(self, draw, box):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        draw.rounded_rectangle(box, radius=10, outline=self.ICON_WHITE, width=4)
        screen_box = [x0 + w * 0.12, y0 + h * 0.18, x1 - w * 0.12, y0 + h * 0.62]
        draw.rectangle(screen_box, outline=self.ICON_WHITE, width=3)
        sx0, sy0, sx1, sy1 = screen_box
        mid = (sy0 + sy1) / 2
        points = []
        steps = 20
        for s in range(steps + 1):
            xx = sx0 + (sx1 - sx0) * s / steps
            yy = mid + math.sin(s / steps * math.pi * 3) * (sy1 - sy0) * 0.25
            points.append((xx, yy))
        draw.line(points, fill=self.ICON_WHITE, width=3, joint="curve")
        for i in range(3):
            kx = x0 + w * (0.25 + i * 0.25)
            ky = y1 - h * 0.14
            draw.ellipse([kx - 6, ky - 6, kx + 6, ky + 6], outline=self.ICON_WHITE, width=3)

    def _icon_generic(self, draw, box):
        draw.rounded_rectangle(box, radius=10, outline=self.ICON_WHITE, width=4)
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        r = min(x1 - x0, y1 - y0) * 0.22
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=self.ICON_WHITE, width=4)

    def render_brand_panel(self, size, title="", subtitle="", seed=7):
        """
        A tall gradient panel (dark indigo, matching the sidebar) used as the
        left-side brand panel on the login screen, with the title/subtitle
        baked directly into the image so no separate overlay widgets are
        needed on top of it.
        """
        path = os.path.join(self.assets_dir, f"brand_panel_{size[0]}x{size[1]}.png")
        if os.path.exists(path):
            return path
        top, bottom = (18, 20, 42), (58, 48, 150)
        img = self._gradient(size, top, bottom).convert("RGBA")
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        self._soft_circles(odraw, size[0], size[1], seed)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        w, h = size
        if title:
            title_font = self._font(30, bold=True)
            draw.text((44, h * 0.62), title, font=title_font, fill=(255, 255, 255, 255))
        if subtitle:
            sub_font = self._font(14)
            draw.text((46, h * 0.62 + 44), subtitle, font=sub_font, fill=(220, 222, 245, 230))

        img.convert("RGB").save(path, "PNG")
        return path

    # ---- card cache key -------------------------------------------------
    def _cache_key(self, facility):
        raw = "|".join(str(facility[k]) for k in
                        ("id", "name", "category", "type", "capacity", "location", "condition"))
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]

    def card_path_for(self, facility):
        return os.path.join(self.cards_dir, f"facility_{facility['id']}_{self._cache_key(facility)}.png")

    def _resolve_uploaded_path(self, facility):
        image_path = facility["image_path"] if "image_path" in facility.keys() else None
        if not image_path:
            return None
        path = image_path if os.path.isabs(image_path) else os.path.join(self.base_dir, image_path)
        return path if os.path.exists(path) else None

    def save_facility_image(self, facility_id, source_path):
        dest_name = f"facility_{facility_id}.png"
        dest_path = os.path.join(self.uploads_dir, dest_name)
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img = ImageOps.fit(img, self.CARD_SIZE, method=Image.LANCZOS)
            img.save(dest_path, "PNG")
        return os.path.relpath(dest_path, self.base_dir)

    # ---- public API -----------------------------------------------------
    def get_facility_card(self, facility, size=None, force=False):
        """
        Returns the filesystem path to a generated PNG card for this facility,
        generating (and caching) it first if needed.
        """
        size = size or self.CARD_SIZE
        uploaded_path = self._resolve_uploaded_path(facility)
        if uploaded_path:
            return uploaded_path
        path = self.card_path_for(facility)
        if not force and os.path.exists(path):
            return path

        # clear any stale cached versions for this facility id
        for fname in os.listdir(self.cards_dir):
            if fname.startswith(f"facility_{facility['id']}_") and fname != os.path.basename(path):
                try:
                    os.remove(os.path.join(self.cards_dir, fname))
                except OSError:
                    pass

        top, bottom = self.CATEGORY_COLORS.get(facility["category"], self.DEFAULT_GRADIENT)
        img = self._gradient(size, top, bottom).convert("RGBA")

        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        self._soft_circles(odraw, size[0], size[1], facility["id"])
        img = Image.alpha_composite(img, overlay)

        # icon panel (right side, large + soft)
        w, h = size
        icon_box = (w * 0.62, h * 0.14, w * 0.94, h * 0.62)
        icon_layer = Image.new("RGBA", size, (0, 0, 0, 0))
        idraw = ImageDraw.Draw(icon_layer)
        icon_fn = self._icon_by_type.get(facility["type"], self._icon_generic)
        icon_fn(idraw, icon_box)
        icon_layer = icon_layer.filter(ImageFilter.GaussianBlur(0))
        img = Image.alpha_composite(img, icon_layer)

        # bottom gradient scrim for text legibility
        scrim = Image.new("RGBA", size, (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(scrim)
        scrim_h = int(h * 0.46)
        for i in range(scrim_h):
            alpha = int(170 * (i / scrim_h) ** 1.4)
            sdraw.line([(0, h - scrim_h + i), (w, h - scrim_h + i)], fill=(10, 12, 20, alpha))
        img = Image.alpha_composite(img, scrim)

        draw = ImageDraw.Draw(img)

        # category chip (top-left)
        chip_font = self._font(20, bold=True)
        chip_text = facility["category"].upper()
        chip_pad_x, chip_pad_y = 14, 7
        tb = draw.textbbox((0, 0), chip_text, font=chip_font)
        chip_w, chip_h = tb[2] - tb[0] + chip_pad_x * 2, tb[3] - tb[1] + chip_pad_y * 2
        chip_xy = [24, 22, 24 + chip_w, 22 + chip_h]
        draw.rounded_rectangle(chip_xy, radius=chip_h / 2, fill=(255, 255, 255, 235))
        chip_color = self.CATEGORY_COLORS.get(facility["category"], self.DEFAULT_GRADIENT)[0]
        draw.text((chip_xy[0] + chip_pad_x, chip_xy[1] + chip_pad_y - tb[1]), chip_text,
                   font=chip_font, fill=chip_color)

        # condition badge (top-right)
        cond = facility["condition"]
        cond_color = self.CONDITION_COLORS.get(cond, (120, 120, 120))
        badge_font = self._font(18, bold=True)
        tb2 = draw.textbbox((0, 0), cond, font=badge_font)
        bw, bh = tb2[2] - tb2[0] + 24, tb2[3] - tb2[1] + 14
        bxy = [w - 24 - bw, 22, w - 24, 22 + bh]
        draw.rounded_rectangle(bxy, radius=bh / 2, fill=(*cond_color, 235))
        draw.text((bxy[0] + 12, bxy[1] + 7 - tb2[1]), cond, font=badge_font, fill=(255, 255, 255, 255))

        # facility name
        name_font = self._font(40, bold=True)
        draw.text((26, h - int(h * 0.32)), facility["name"], font=name_font, fill=(255, 255, 255, 255))

        # subtitle: type - location - capacity
        sub_font = self._font(19)
        cap = facility["capacity"] or 0
        subtitle = f"{facility['type']}   •   {facility['location'] or 'Unassigned'}   •   Capacity {cap}"
        draw.text((28, h - int(h * 0.32) + 50), subtitle, font=sub_font, fill=(235, 236, 240, 255))

        img.convert("RGB").save(path, "PNG")
        return path

    def get_placeholder_card(self, size=None, message="No facilities to display"):
        size = size or self.CARD_SIZE
        path = os.path.join(self.cards_dir, "_placeholder.png")
        img = self._gradient(size, self.DEFAULT_GRADIENT[0], self.DEFAULT_GRADIENT[1]).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = self._font(26, bold=True)
        tb = draw.textbbox((0, 0), message, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text(((size[0] - tw) / 2, (size[1] - th) / 2), message, font=font, fill=(255, 255, 255, 230))
        img.convert("RGB").save(path, "PNG")
        return path


class PersonCardRenderer:
    """
    Renders and caches 'people' imagery for the Manage Users directory and
    profile screens - two flavours of the same underlying photo:

      * avatar  - a square headshot-style image: the person's own uploaded
                   photo if they have one, otherwise a procedurally drawn
                   circle-on-gradient with their initials, colour-keyed off
                   their name so the same person always gets the same colour.
      * showcase card - a wide 2:1 card (same proportions as a facility
                   card) combining that avatar with a name/role/status
                   overlay, so the Manage Users tab can run a slideshow of
                   the user directory the same way the Dashboard/Facility
                   tabs do for facilities.
    """

    AVATAR_SIZE = (320, 320)
    CARD_SIZE = (760, 380)  # matches FacilityCardRenderer.CARD_SIZE

    ROLE_COLORS = {
        "Student": ((66, 99, 235), (110, 150, 255)),
        "Faculty": ((15, 148, 120), (52, 199, 165)),
        "Staff":   ((235, 124, 32), (255, 170, 76)),
        "Admin":   ((142, 68, 173), (186, 120, 219)),
    }
    DEFAULT_GRADIENT = ((90, 96, 110), (140, 146, 160))

    def __init__(self, base_dir=None, font_helper=None, gradient_helper=None, soft_circles_helper=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.assets_dir = os.path.join(self.base_dir, "assets")
        self.avatars_dir = os.path.join(self.assets_dir, "avatars")
        self.cards_dir = os.path.join(self.assets_dir, "people_cards")
        self.profile_pics_dir = os.path.join(self.assets_dir, "profile_pics")
        for d in (self.avatars_dir, self.cards_dir, self.profile_pics_dir):
            os.makedirs(d, exist_ok=True)
        # Reuse FacilityCardRenderer's drawing helpers rather than duplicate
        # them - passed in from the shared instance below.
        self._font = font_helper
        self._gradient = gradient_helper
        self._soft_circles = soft_circles_helper

    # ---- palette --------------------------------------------------------
    def _color_pair_for(self, role, name):
        if role in self.ROLE_COLORS:
            return self.ROLE_COLORS[role]
        return self.DEFAULT_GRADIENT

    def _initials(self, name):
        words = [w for w in (name or "").split() if w]
        letters = "".join(w[0] for w in words[:2]).upper()
        return letters or "?"

    # ---- uploaded photo storage ------------------------------------------
    def save_profile_photo(self, kind, key, source_path):
        """
        Crops the chosen image to a centered square and saves it under
        assets/profile_pics/{kind}_{key}.png (kind is 'user' or 'admin',
        key is the user id or admin username). Returns the saved path.
        """
        safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(key))
        dest_path = os.path.join(self.profile_pics_dir, f"{kind}_{safe_key}.png")
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            w, h = img.size
            side = min(w, h)
            left, top = (w - side) // 2, (h - side) // 2
            img = img.crop((left, top, left + side, top + side))
            img = img.resize(self.AVATAR_SIZE, Image.LANCZOS)
            img.save(dest_path, "PNG")
        return dest_path

    # ---- generated placeholder avatar ------------------------------------
    def _generated_avatar_path(self, kind, key, name):
        safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(key))
        digest = hashlib.md5(f"{kind}:{key}:{name}".encode("utf-8")).hexdigest()[:10]
        return os.path.join(self.avatars_dir, f"{kind}_{safe_key}_{digest}.png")

    def get_avatar(self, kind, key, name, role=None, custom_path=None, force=False):
        """
        Returns a filesystem path to a square avatar image for this person:
        their uploaded photo if `custom_path` points at one, otherwise a
        cached, procedurally-generated initials-on-gradient avatar.
        """
        if custom_path:
            resolved = custom_path if os.path.isabs(custom_path) else os.path.join(self.base_dir, custom_path)
            if os.path.exists(resolved):
                return resolved

        path = self._generated_avatar_path(kind, key, name)
        if not force and os.path.exists(path):
            return path

        size = self.AVATAR_SIZE
        top, bottom = self._color_pair_for(role, name)
        img = self._gradient(size, top, bottom).convert("RGBA") if self._gradient else \
            Image.new("RGBA", size, top)
        draw = ImageDraw.Draw(img)
        if self._soft_circles:
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            seed = int(hashlib.md5(f"{kind}{key}".encode()).hexdigest(), 16) % (2 ** 31)
            self._soft_circles(odraw, size[0], size[1], seed)
            img = Image.alpha_composite(img, overlay)
            draw = ImageDraw.Draw(img)

        initials = self._initials(name)
        font = self._font(int(size[0] * 0.34), bold=True) if self._font else ImageFont.load_default()
        tb = draw.textbbox((0, 0), initials, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        draw.text(((size[0] - tw) / 2 - tb[0], (size[1] - th) / 2 - tb[1]),
                   initials, font=font, fill=(255, 255, 255, 235))
        img.convert("RGB").save(path, "PNG")
        return path

    # ---- directory showcase card (for the Manage Users carousel) --------
    def get_person_card(self, kind, key, name, role="", subtitle="", status="", custom_path=None, force=False):
        """
        Wide 2:1 'photo card' pairing an avatar with name/role/status text,
        cached on disk - same idea as FacilityCardRenderer.get_facility_card,
        so Manage Users can run a slideshow the same way Facility/Dashboard
        tabs already do.
        """
        digest = hashlib.md5(f"{kind}:{key}:{name}:{role}:{subtitle}:{status}:{bool(custom_path)}"
                              .encode("utf-8")).hexdigest()[:16]
        safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(key))
        path = os.path.join(self.cards_dir, f"{kind}_{safe_key}_{digest}.png")
        if not force and os.path.exists(path):
            return path

        for fname in os.listdir(self.cards_dir):
            if fname.startswith(f"{kind}_{safe_key}_") and fname != os.path.basename(path):
                try:
                    os.remove(os.path.join(self.cards_dir, fname))
                except OSError:
                    pass

        size = self.CARD_SIZE
        top, bottom = self._color_pair_for(role, name)
        img = self._gradient(size, top, bottom).convert("RGBA") if self._gradient else \
            Image.new("RGBA", size, top)
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        if self._soft_circles:
            seed = int(hashlib.md5(f"{kind}{key}".encode()).hexdigest(), 16) % (2 ** 31)
            self._soft_circles(odraw, size[0], size[1], seed)
        img = Image.alpha_composite(img, overlay)

        # avatar photo, inset on the right side of the card
        avatar_path = self.get_avatar(kind, key, name, role=role, custom_path=custom_path)
        av_size = int(size[1] * 0.66)
        avatar_img = Image.open(avatar_path).convert("RGBA").resize((av_size, av_size), Image.LANCZOS)
        mask = Image.new("L", (av_size, av_size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, av_size, av_size], fill=255)
        av_x, av_y = size[0] - av_size - 46, (size[1] - av_size) // 2
        ring = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse(
            [av_x - 5, av_y - 5, av_x + av_size + 5, av_y + av_size + 5],
            outline=(255, 255, 255, 220), width=5)
        img = Image.alpha_composite(img, ring)
        img.paste(avatar_img, (av_x, av_y), mask)

        draw = ImageDraw.Draw(img)
        w, h = size
        if role:
            chip_font = self._font(20, bold=True) if self._font else ImageFont.load_default()
            chip_text = role.upper()
            tb = draw.textbbox((0, 0), chip_text, font=chip_font)
            chip_w = tb[2] - tb[0] + 28
            chip_h = tb[3] - tb[1] + 14
            chip_xy = [24, 22, 24 + chip_w, 22 + chip_h]
            draw.rounded_rectangle(chip_xy, radius=chip_h / 2, fill=(255, 255, 255, 235))
            draw.text((chip_xy[0] + 14, chip_xy[1] + 7 - tb[1]), chip_text, font=chip_font, fill=top)
        if status:
            badge_font = self._font(16, bold=True) if self._font else ImageFont.load_default()
            status_color = (34, 160, 90) if "set" in status.lower() and "not" not in status.lower() \
                else (196, 76, 36)
            tb2 = draw.textbbox((0, 0), status, font=badge_font)
            bw, bh = tb2[2] - tb2[0] + 22, tb2[3] - tb2[1] + 12
            bxy = [24, h - 22 - bh, 24 + bw, h - 22]
            draw.rounded_rectangle(bxy, radius=bh / 2, fill=(*status_color, 230))
            draw.text((bxy[0] + 11, bxy[1] + 6 - tb2[1]), status, font=badge_font, fill=(255, 255, 255, 255))

        name_font = self._font(34, bold=True) if self._font else ImageFont.load_default()
        draw.text((26, h - int(h * 0.34)), name, font=name_font, fill=(255, 255, 255, 255))
        if subtitle:
            sub_font = self._font(17) if self._font else ImageFont.load_default()
            draw.text((28, h - int(h * 0.34) + 44), subtitle, font=sub_font, fill=(235, 236, 240, 255))

        img.convert("RGB").save(path, "PNG")
        return path


# --------------------------------------------------------------------------
# Shared instance + backward-compatible module-level functions, so existing
# call sites (`assets.get_facility_card(f)`) keep working unchanged.
# --------------------------------------------------------------------------
_renderer = FacilityCardRenderer()
_person_renderer = PersonCardRenderer(
    base_dir=_renderer.base_dir,
    font_helper=_renderer._font,
    gradient_helper=_renderer._gradient,
    soft_circles_helper=_renderer._soft_circles,
)

CARD_SIZE = _renderer.CARD_SIZE
ASSETS_DIR = _renderer.assets_dir
CARDS_DIR = _renderer.cards_dir
UPLOADS_DIR = _renderer.uploads_dir


def card_path_for(facility):
    return _renderer.card_path_for(facility)


def get_facility_card(facility, size=CARD_SIZE, force=False):
    return _renderer.get_facility_card(facility, size=size, force=force)


def get_placeholder_card(size=CARD_SIZE, message="No facilities to display"):
    return _renderer.get_placeholder_card(size=size, message=message)


def get_brand_panel(size, title="", subtitle=""):
    return _renderer.render_brand_panel(size, title=title, subtitle=subtitle)


def save_facility_image(facility_id, source_path):
    return _renderer.save_facility_image(facility_id, source_path)


# ---- people: avatars, uploaded photos, directory showcase cards ---------
def save_profile_photo(kind, key, source_path):
    """kind is 'user' or 'admin'; key is the user id or admin username."""
    return _person_renderer.save_profile_photo(kind, key, source_path)


def get_avatar(kind, key, name, role=None, custom_path=None, force=False):
    return _person_renderer.get_avatar(kind, key, name, role=role,
                                        custom_path=custom_path, force=force)


def get_person_card(kind, key, name, role="", subtitle="", status="", custom_path=None, force=False):
    return _person_renderer.get_person_card(kind, key, name, role=role, subtitle=subtitle,
                                             status=status, custom_path=custom_path, force=force)
