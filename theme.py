"""
theme.py
--------
Central colour palette and ttk style configuration for the app, including
hover/active-state styling for buttons and tabs (ttk widgets automatically
switch to the 'active' style state on mouse-over, so mapping that state is
enough to get real hover feedback without any manual event binding).

Everything lives on the `AppTheme` class now (palette as class attributes,
`apply()` / `style_treeview_tags()` as methods) instead of being spread
across bare module-level names and functions.

For backward compatibility with existing call sites elsewhere in the app
(`theme.BG`, `theme.apply_theme(root)`, `theme.style_treeview_tags(tree)`,
etc.), the module still exposes the same names at the top level - they're
just thin references to `AppTheme` now rather than independent globals.

--------------------------------------------------------------------------
Light / dark mode
--------------------------------------------------------------------------
Two full palettes are defined below (`LIGHT` and `DARK`). `AppTheme` starts
out on the light palette. Call `theme.set_mode("dark")` (or
`theme.toggle_mode()`) to swap every colour attribute over, refresh the
ttk styles on a given Tk root, and update the module-level names so any
code that reads `theme.BG` etc. picks up the new colours immediately.

Because plain `tk.Frame`/`tk.Label` widgets bake their colours in as literal
strings at creation time, switching modes only repaints *new* widgets
correctly - existing widgets on screen need to be rebuilt for the change to
show. The app handles that by rebuilding its UI after a mode switch; this
module is only responsible for holding/swapping the palette itself.
"""

from tkinter import ttk


# ==========================================================================
# Palettes
# ==========================================================================
# Sidebar / shadow colours are intentionally the same in both modes - the
# sidebar is a fixed dark "shell" regardless of whether the main content
# area is in light or dark mode.
_SIDEBAR_SHARED = {
    "SIDEBAR_BG": "#15162e",
    "SIDEBAR_BG_ACTIVE": "#23244a",
    "SIDEBAR_BG_HOVER": "#1c1d3c",
    "SIDEBAR_TEXT": "#e9eafa",
    "SIDEBAR_TEXT_ACTIVE": "#ffffff",
    "SIDEBAR_TEXT_MUTED": "#8b8ec2",
    "SIDEBAR_ACCENT": "#8b7bff",
}

# Status/condition badge colours and stat-tile accents also stay the same
# across modes - they're saturated enough to read fine on both surfaces.
_ACCENTS_SHARED = {
    "STATUS_COLORS": {
        "Pending": "#f79009",
        "Approved": "#12b76a",
        "Cancelled": "#f04438",
        "Completed": "#98a2b3",
    },
    "CONDITION_COLORS": {
        "Good": "#12b76a",
        "Fair": "#f79009",
        "Under Maintenance": "#e04f16",
        "Out of Service": "#b42318",
    },
    "STAT_ACCENTS": ["#5b5fef", "#12b76a", "#f79009", "#0891b2", "#d6409f"],
}


LIGHT = {
    "BG": "#f2f3fa",
    "SURFACE": "#ffffff",
    "BORDER": "#e5e7f2",
    "TEXT": "#191b2b",
    "MUTED_TEXT": "#6c7089",

    "PRIMARY": "#5b5fef",
    "PRIMARY_HOVER": "#4b4fe0",
    "PRIMARY_PRESSED": "#3d40c9",
    "PRIMARY_SOFT": "#eef0ff",

    "SUCCESS": "#12b76a",
    "SUCCESS_HOVER": "#0e9c5a",

    "DANGER": "#f04438",
    "DANGER_HOVER": "#d92d20",

    "NEUTRAL": "#f0f1f8",
    "NEUTRAL_HOVER": "#e2e4f3",

    "ROW_ALT": "#f8f9fd",
    "ROW_HOVER": "#eef0ff",
    "ROW_SELECT": "#dfe2ff",

    "SHADOW": "#d5d8ea",
    **_SIDEBAR_SHARED,
    **_ACCENTS_SHARED,
}

DARK = {
    "BG": "#14152a",
    "SURFACE": "#1e1f3b",
    "BORDER": "#4c4f80",
    "TEXT": "#eef0ff",
    "MUTED_TEXT": "#a0a3c9",

    "PRIMARY": "#7b7fff",
    "PRIMARY_HOVER": "#9093ff",
    "PRIMARY_PRESSED": "#6266e6",
    "PRIMARY_SOFT": "#2a2c56",

    "SUCCESS": "#2fd88a",
    "SUCCESS_HOVER": "#26c07b",

    "DANGER": "#ff6259",
    "DANGER_HOVER": "#ff453b",

    "NEUTRAL": "#282a4e",
    "NEUTRAL_HOVER": "#33355e",

    "ROW_ALT": "#1a1b36",
    "ROW_HOVER": "#282a54",
    "ROW_SELECT": "#3a3d70",

    "SHADOW": "#0c0d1c",
    **_SIDEBAR_SHARED,
    **_ACCENTS_SHARED,
}

_PALETTE_KEYS = list(LIGHT.keys())


class AppTheme:
    """Palette + ttk style configuration for the whole application."""

    MODE = "light"
    FONT_FAMILY = "Segoe UI"
    TOPBAR_BG = LIGHT["SURFACE"]

    def __init__(self, root=None):
        """Optionally applies the theme immediately if a Tk root is given."""
        self.style = None
        if root is not None:
            self.apply(root)

    # ---- mode switching ---------------------------------------------------
    @classmethod
    def set_mode(cls, mode, root=None):
        """Swap every palette attribute to `mode` ('light' or 'dark').

        Also refreshes the module-level names (`theme.BG`, etc.) so any code
        reading them directly sees the new colours right away. If `root` is
        given, its ttk.Style is re-configured immediately as well - plain tk
        widgets already on screen still need to be rebuilt by the caller."""
        palette = DARK if mode == "dark" else LIGHT
        for key, value in palette.items():
            setattr(cls, key, value)
        cls.MODE = "dark" if mode == "dark" else "light"
        cls.TOPBAR_BG = cls.SURFACE
        _sync_globals()
        if root is not None:
            cls.apply(root)
        return cls.MODE

    @classmethod
    def toggle_mode(cls, root=None):
        """Flip between light and dark, returning the new mode name."""
        return cls.set_mode("light" if cls.MODE == "dark" else "dark", root=root)

    # ---- ttk style setup --------------------------------------------------
    @classmethod
    def apply(cls, root):
        """Configures `root` and returns the ttk.Style instance used."""
        root.configure(bg=cls.BG)
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # The combobox drop-down list is a plain Tk Listbox, not a ttk
        # widget, so it needs the option database rather than style.map.
        root.option_add("*TCombobox*Listbox.background", cls.SURFACE)
        root.option_add("*TCombobox*Listbox.foreground", cls.TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", cls.PRIMARY)
        root.option_add("*TCombobox*Listbox.selectForeground", "white")
        root.option_add("*TCombobox*Listbox.font", (cls.FONT_FAMILY, 9))

        style.configure(".", background=cls.BG, foreground=cls.TEXT, font=(cls.FONT_FAMILY, 10))
        style.configure("TFrame", background=cls.BG)
        style.configure("Surface.TFrame", background=cls.SURFACE)
        style.configure("TLabelframe", background=cls.BG, borderwidth=1, relief="solid",
                         bordercolor=cls.BORDER)
        style.configure("TLabelframe.Label", background=cls.BG, foreground=cls.TEXT,
                         font=(cls.FONT_FAMILY, 10, "bold"))
        style.configure("TLabel", background=cls.BG, foreground=cls.TEXT)
        style.configure("Muted.TLabel", background=cls.BG, foreground=cls.MUTED_TEXT,
                         font=(cls.FONT_FAMILY, 9))
        style.configure("Heading.TLabel", background=cls.BG, foreground=cls.TEXT,
                         font=(cls.FONT_FAMILY, 19, "bold"))
        style.configure("SubHeading.TLabel", background=cls.BG, foreground=cls.TEXT,
                         font=(cls.FONT_FAMILY, 12, "bold"))
        style.configure("Card.TLabelframe", background=cls.SURFACE, bordercolor=cls.BORDER,
                         borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=cls.SURFACE, foreground=cls.PRIMARY,
                         font=(cls.FONT_FAMILY, 10, "bold"))
        style.configure("OnCard.TLabel", background=cls.SURFACE, foreground=cls.TEXT)
        style.configure("OnCardHeading.TLabel", background=cls.SURFACE, foreground=cls.TEXT,
                         font=(cls.FONT_FAMILY, 12, "bold"))
        style.configure("OnCardMuted.TLabel", background=cls.SURFACE, foreground=cls.MUTED_TEXT,
                         font=(cls.FONT_FAMILY, 9))
        style.configure("CardValue.TLabel", background=cls.SURFACE, foreground=cls.PRIMARY,
                         font=(cls.FONT_FAMILY, 22, "bold"))
        style.configure("CardTitle.TLabel", background=cls.SURFACE, foreground=cls.MUTED_TEXT,
                         font=(cls.FONT_FAMILY, 9))

        # ---- notebook / tabs ----
        style.configure("TNotebook", background=cls.BG, borderwidth=0, tabmargins=(6, 8, 6, 0))
        style.configure("TNotebook.Tab", background=cls.NEUTRAL, foreground=cls.MUTED_TEXT,
                         padding=(16, 9), font=(cls.FONT_FAMILY, 10, "bold"), borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", cls.SURFACE), ("active", cls.NEUTRAL_HOVER)],
                  foreground=[("selected", cls.PRIMARY), ("active", cls.TEXT)])

        # ---- generic entry / combobox, with a visible focus ring ----
        # Fields keep the normal dark surface background - only the outline
        # and the drop-down arrow use a brighter colour so they stay easy
        # to see against a dark background.
        style.configure("TEntry", fieldbackground=cls.SURFACE, foreground=cls.TEXT,
                         bordercolor=cls.BORDER,
                         lightcolor=cls.BORDER, darkcolor=cls.BORDER, padding=6,
                         insertcolor=cls.TEXT)
        style.map("TEntry",
                  bordercolor=[("focus", cls.PRIMARY)],
                  lightcolor=[("focus", cls.PRIMARY)],
                  darkcolor=[("focus", cls.PRIMARY)])
        style.configure("TCombobox", fieldbackground=cls.SURFACE, foreground=cls.TEXT,
                         background=cls.SURFACE, bordercolor=cls.BORDER,
                         arrowsize=13, padding=5, arrowcolor=cls.TEXT)
        style.map("TCombobox", fieldbackground=[("readonly", cls.SURFACE)],
                  foreground=[("readonly", cls.TEXT)],
                  bordercolor=[("focus", cls.PRIMARY)],
                  selectbackground=[("readonly", cls.SURFACE)],
                  selectforeground=[("readonly", cls.TEXT)],
                  background=[("readonly", cls.SURFACE), ("active", cls.NEUTRAL_HOVER)],
                  arrowcolor=[("disabled", cls.MUTED_TEXT), ("active", cls.PRIMARY)])

        # ---- buttons: base + semantic variants, each with a real hover state ----
        style.configure("TButton", padding=(14, 8), font=(cls.FONT_FAMILY, 9, "bold"),
                         borderwidth=0)

        style.configure("Primary.TButton", background=cls.PRIMARY, foreground="white")
        style.map("Primary.TButton",
                  background=[("pressed", cls.PRIMARY_PRESSED), ("active", cls.PRIMARY_HOVER)],
                  foreground=[("disabled", cls.MUTED_TEXT)])

        style.configure("Success.TButton", background=cls.SUCCESS, foreground="white")
        style.map("Success.TButton",
                  background=[("pressed", "#0b8552"), ("active", cls.SUCCESS_HOVER)])

        style.configure("Danger.TButton", background=cls.DANGER, foreground="white")
        style.map("Danger.TButton",
                  background=[("pressed", "#b42318"), ("active", cls.DANGER_HOVER)])

        style.configure("Neutral.TButton", background=cls.NEUTRAL, foreground=cls.TEXT)
        style.map("Neutral.TButton",
                  background=[("pressed", cls.ROW_SELECT), ("active", cls.NEUTRAL_HOVER)])

        style.configure("Exit.TButton", background=cls.DANGER, foreground="white")
        style.map("Exit.TButton",
                  background=[("pressed", "#b42318"), ("active", cls.DANGER_HOVER)])

        style.configure("Ghost.TButton", background=cls.BG, foreground=cls.PRIMARY, padding=(9, 6))
        style.map("Ghost.TButton", background=[("active", cls.PRIMARY_SOFT)])

        style.configure("Nav.TButton", background=cls.SURFACE, foreground=cls.PRIMARY,
                         font=(cls.FONT_FAMILY, 14, "bold"), padding=(10, 4))
        style.map("Nav.TButton", background=[("active", cls.PRIMARY_SOFT)])

        # ---- treeview: taller rows and a calmer header for a less cramped grid ----
        style.configure("Treeview", background=cls.SURFACE, fieldbackground=cls.SURFACE,
                         foreground=cls.TEXT, rowheight=30, borderwidth=0,
                         font=(cls.FONT_FAMILY, 9))
        style.configure("Treeview.Heading", background=cls.NEUTRAL, foreground=cls.TEXT,
                         font=(cls.FONT_FAMILY, 9, "bold"), padding=(8, 8), relief="flat")
        style.map("Treeview.Heading", background=[("active", cls.NEUTRAL_HOVER)])
        style.map("Treeview",
                  background=[("selected", cls.ROW_SELECT)],
                  foreground=[("selected", cls.TEXT)])

        return style

    # Kept as an alias so `theme.apply_theme(root)` call sites don't need to change.
    apply_theme = apply

    @classmethod
    def style_treeview_tags(cls, tree):
        """Apply the shared alternating-row / hover / status tag palette to a Treeview."""
        tree.tag_configure("oddrow", background=cls.ROW_ALT)
        tree.tag_configure("evenrow", background=cls.SURFACE)
        tree.tag_configure("hoverrow", background=cls.ROW_HOVER)
        for status, color in cls.STATUS_COLORS.items():
            tree.tag_configure(f"status_{status}", foreground=color,
                                font=(cls.FONT_FAMILY, 9, "bold"))
        for cond, color in cls.CONDITION_COLORS.items():
            tree.tag_configure(f"cond_{cond}", foreground=color,
                                font=(cls.FONT_FAMILY, 9, "bold"))


# Seed AppTheme's class attributes with the light palette to start.
for _k, _v in LIGHT.items():
    setattr(AppTheme, _k, _v)


# --------------------------------------------------------------------------
# Backward-compatible module-level names.
#
# The rest of the app (main.py, widgets.py, id_scanner.py) refers to colours
# and helpers as `theme.BG`, `theme.apply_theme(root)`, etc. Rather than
# rewrite every one of those call sites, the module keeps exposing the same
# names - they just delegate to `AppTheme` now instead of being independent
# globals, so there is a single, real source of truth behind them.
#
# `_sync_globals()` re-copies AppTheme's current attributes onto these module
# level names; it's called automatically whenever the mode changes.
# --------------------------------------------------------------------------
def _sync_globals():
    g = globals()
    for key in _PALETTE_KEYS:
        g[key] = getattr(AppTheme, key)
    g["FONT_FAMILY"] = AppTheme.FONT_FAMILY
    g["TOPBAR_BG"] = AppTheme.TOPBAR_BG
    g["MODE"] = AppTheme.MODE


_sync_globals()

apply_theme = AppTheme.apply
style_treeview_tags = AppTheme.style_treeview_tags


def set_mode(mode, root=None):
    """Module-level convenience for `AppTheme.set_mode`."""
    return AppTheme.set_mode(mode, root=root)


def toggle_mode(root=None):
    """Module-level convenience for `AppTheme.toggle_mode`."""
    return AppTheme.toggle_mode(root=root)


def is_dark():
    return AppTheme.MODE == "dark"


# ==========================================================================
# Live re-colouring (no UI rebuild)
# ==========================================================================
# Plain tk widgets (Frame/Label/Canvas/...) bake their colours in as literal
# strings at creation time, so switching `AppTheme`'s attributes alone does
# nothing to widgets already on screen - that's why the app used to call
# `_build_ui()` again after every toggle. That rebuild is a "hard refresh":
# it drops scroll position, in-progress form input, table selection, etc.
#
# `live_recolor()` instead walks the *existing* widget tree exactly once and
# swaps each widget's colour options directly: for every colour a widget is
# currently using, look up which palette key that colour belongs to in the
# *old* palette, and set that option to the *new* palette's value for the
# same key. ttk widgets are skipped entirely here - they already repaint
# from `AppTheme.apply()`/the style system, and forcing an instance-level
# colour override on one (e.g. a ttk.Button) can make it stop drawing its
# text altogether, which is worse than not recolouring it live.
#
# Sidebar colours and the status/condition/stat-accent colours are shared
# between LIGHT and DARK on purpose (see _SIDEBAR_SHARED/_ACCENTS_SHARED
# above) so they never need to change - they're deliberately excluded from
# the lookup below so a colour like pure white (used both as LIGHT's SURFACE
# and as the shared SIDEBAR_TEXT_ACTIVE) always resolves to the one that
# actually changes between modes.
_COLOR_OPTIONS = (
    "bg", "fg", "background", "foreground",
    "activebackground", "activeforeground",
    "highlightbackground", "highlightcolor",
    "selectcolor", "disabledforeground",
    "insertbackground", "readonlybackground", "troughcolor",
)

_CANVAS_ITEM_OPTIONS = ("fill", "outline", "activefill", "activeoutline")

_NON_SHARED_KEYS = [k for k in _PALETTE_KEYS if k not in _SIDEBAR_SHARED]


def _reverse_palette(mode):
    palette = DARK if mode == "dark" else LIGHT
    reverse = {}
    for key in _NON_SHARED_KEYS:
        value = palette.get(key)
        if isinstance(value, str):
            reverse[value.lower()] = key
    return reverse


def _recolor_widget(widget, reverse, new_palette):
    import tkinter as _tk
    from tkinter import ttk as _ttk

    if isinstance(widget, _ttk.Widget):
        # ttk widgets (Button, Entry, Combobox, Treeview, ...) already
        # repaint from the style system via AppTheme.apply()/set_mode() -
        # forcing an instance-level "foreground"/"background" override here
        # bypasses that and can silently drop the widget's text rendering
        # (seen on ttk.Button - the label stops drawing). Treeview row tags
        # are the one thing styles can't reach, so that's still refreshed.
        if isinstance(widget, _ttk.Treeview):
            AppTheme.style_treeview_tags(widget)
        return

    try:
        current = widget.configure()
    except Exception:
        current = None

    if current is not None:
        changes = {}
        for opt in _COLOR_OPTIONS:
            if opt not in current:
                continue
            try:
                value = str(widget.cget(opt))
            except Exception:
                continue
            key = reverse.get(value.lower())
            if key:
                changes[opt] = new_palette[key]
        if changes:
            try:
                widget.configure(**changes)
            except Exception:
                pass

    if isinstance(widget, _tk.Canvas):
        for item in widget.find_all():
            changes = {}
            for opt in _CANVAS_ITEM_OPTIONS:
                try:
                    value = widget.itemcget(item, opt)
                except Exception:
                    continue
                if not value:
                    continue
                key = reverse.get(str(value).lower())
                if key:
                    changes[opt] = new_palette[key]
            if changes:
                try:
                    widget.itemconfigure(item, **changes)
                except Exception:
                    pass

    # Treeviews colour their rows via tags rather than widget options.
    try:
        from tkinter import ttk as _ttk
        if isinstance(widget, _ttk.Treeview):
            AppTheme.style_treeview_tags(widget)
    except Exception:
        pass


def live_recolor(root, old_mode, new_mode):
    """Re-colour `root` and every descendant in place, without destroying or
    rebuilding any widget. Call this *after* `set_mode(new_mode, root=root)`
    so ttk styles are already updated; this handles the plain tk widgets
    that styles can't reach."""
    if old_mode == new_mode:
        return
    reverse = _reverse_palette(old_mode)
    new_palette = DARK if new_mode == "dark" else LIGHT

    def walk(widget):
        _recolor_widget(widget, reverse, new_palette)
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            walk(child)

    walk(root)