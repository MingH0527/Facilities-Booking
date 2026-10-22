"""
widgets.py
----------
Reusable UI widgets shared across tabs:

  * ImageCarousel   - a slideshow of facility photo-cards with prev/next
                       arrows, dot indicators, auto-play, and pause-on-hover.
  * attach_row_hover - gives a ttk.Treeview a live highlight on the row under
                       the mouse cursor, without disturbing its other tags.
  * confirm          - a small wrapper around messagebox.askyesno so every
                       call site reads the same way.
  * ToastManager     - non-blocking "toast" notifications (success/info/
                       warning/error) that slide in near the top-right of a
                       window and dismiss themselves, instead of a modal
                       messagebox stealing focus for routine confirmations.
  * EmptyState       - a friendly placeholder overlay for a Treeview's
                       container when a table has zero rows.
"""

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox, font as tkfont
from PIL import Image, ImageTk

import theme


def confirm(title, message, danger=False):
    """Uniform yes/no confirmation prompt used before every state-changing action."""
    icon = "warning" if danger else "question"
    return messagebox.askyesno(title, message, icon=icon)


# ==========================================================================
# Toast notifications
# ==========================================================================
class Toast(tk.Toplevel):
    """
    A single self-dismissing notification card, borderless and positioned
    near the top-right corner of `parent`. Prefer `ToastManager.show()` /
    an app's `show_toast()` over constructing this directly, since the
    manager handles stacking multiple toasts and reflowing them as each
    one closes.
    """

    DURATION_MS = 3200
    WIDTH = 300

    _KIND_STYLE = {
        "success": ("SUCCESS", "\u2713"),
        "error": ("DANGER", "\u2715"),
        "warning": (None, "\u26A0"),   # amber isn't in the palette dict - set directly below
        "info": ("PRIMARY", "\u2139"),
    }

    def __init__(self, parent, message, kind="success", index=0, on_close=None):
        super().__init__(parent)
        self.parent = parent
        self.on_close = on_close
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        accent_key, icon = self._KIND_STYLE.get(kind, self._KIND_STYLE["info"])
        accent = "#f79009" if kind == "warning" else getattr(theme, accent_key or "PRIMARY")

        card = tk.Frame(self, bg=theme.SURFACE, highlightthickness=1,
                         highlightbackground=theme.BORDER, highlightcolor=theme.BORDER)
        card.pack(fill="both", expand=True)

        stripe = tk.Frame(card, bg=accent, width=4)
        stripe.pack(side="left", fill="y")

        body = tk.Frame(card, bg=theme.SURFACE)
        body.pack(side="left", fill="both", expand=True, padx=(10, 24), pady=10)

        top = tk.Frame(body, bg=theme.SURFACE)
        top.pack(fill="x", anchor="w")
        tk.Label(top, text=icon, bg=theme.SURFACE, fg=accent,
                 font=(theme.FONT_FAMILY, 10, "bold")).pack(side="left")
        tk.Label(top, text=message, bg=theme.SURFACE, fg=theme.TEXT, wraplength=220,
                 justify="left", font=(theme.FONT_FAMILY, 9)).pack(side="left", padx=(8, 0))

        close = tk.Label(card, text="\u2715", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                          font=(theme.FONT_FAMILY, 8), cursor="hand2")
        close.place(relx=1.0, rely=0.0, anchor="ne", x=-6, y=6)
        close.bind("<Button-1>", lambda e: self._dismiss())

        self.update_idletasks()
        self.geometry(f"{self.WIDTH}x{self.winfo_reqheight()}")
        self.reposition(index)
        self._timer = self.after(self.DURATION_MS, self._dismiss)

    def reposition(self, index):
        """Move to the `index`-th slot in the stack (0 = closest to the top)."""
        try:
            h = self.winfo_height() or self.winfo_reqheight()
            px, py = self.parent.winfo_rootx(), self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            x = px + pw - self.WIDTH - 24
            y = py + 24 + index * (h + 10)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _dismiss(self):
        try:
            self.after_cancel(self._timer)
        except Exception:
            pass
        if self.on_close:
            self.on_close(self)
        try:
            self.destroy()
        except Exception:
            pass


class ToastManager:
    """One instance per app window. Keeps a stack of active `Toast` popups
    and reflows the remaining ones whenever one expires or is dismissed."""

    def __init__(self, root):
        self.root = root
        self._active = []

    def show(self, message, kind="success"):
        toast = Toast(self.root, message, kind=kind, index=len(self._active),
                       on_close=self._on_closed)
        self._active.append(toast)
        return toast

    def _on_closed(self, toast):
        if toast in self._active:
            self._active.remove(toast)
        for i, t in enumerate(self._active):
            try:
                t.reposition(i)
            except Exception:
                pass


# ==========================================================================
# Empty-state placeholder (for a Treeview with zero rows)
# ==========================================================================
class EmptyState(tk.Frame):
    """
    An overlay placeholder shown in place of an empty table. Construct it as
    a child of the same container the Treeview lives in, then call `.show()`
    from `refresh()` once you know the row count is zero, or `.hide()`
    otherwise - it simply layers itself over the tree with `.place()`.
    """

    def __init__(self, parent, icon="\U0001F4ED", title="Nothing here yet",
                 subtitle=""):
        super().__init__(parent, bg=theme.SURFACE)
        wrap = tk.Frame(self, bg=theme.SURFACE)
        wrap.place(relx=0.5, rely=0.42, anchor="center")
        tk.Label(wrap, text=icon, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 28)).pack()
        tk.Label(wrap, text=title, bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 11, "bold")).pack(pady=(8, 2))
        if subtitle:
            tk.Label(wrap, text=subtitle, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                     wraplength=260, justify="center",
                     font=(theme.FONT_FAMILY, 9)).pack()

    def show(self):
        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()

    def hide(self):
        self.place_forget()


# ==========================================================================
# Date entry: type digits and the '-' separators fill themselves in, or
# click the calendar icon to pick a date visually instead of typing at all.
# ==========================================================================
class _CalendarPopup(tk.Toplevel):
    """Small themed month-calendar shown by DateEntry's calendar button."""

    def __init__(self, master, on_pick, initial=None):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg=theme.BORDER)
        self.on_pick = on_pick
        today = date.today()
        initial = initial or today
        self.view_year = initial.year
        self.view_month = initial.month
        self.selected = initial
        self.mode = "day"  # "day" (default grid) or "month" (quick jump picker)

        card = tk.Frame(self, bg=theme.SURFACE)
        card.pack(padx=1, pady=1)

        header = tk.Frame(card, bg=theme.SURFACE)
        header.pack(fill="x", padx=10, pady=(10, 4))
        self.prev_btn = tk.Button(header, text="\u2039", command=self._on_prev, bd=0,
                                   bg=theme.SURFACE, fg=theme.PRIMARY, activebackground=theme.NEUTRAL_HOVER,
                                   activeforeground=theme.PRIMARY, font=(theme.FONT_FAMILY, 11, "bold"),
                                   cursor="hand2", relief="flat")
        self.prev_btn.pack(side="left")
        self.title_lbl = tk.Label(header, text="", bg=theme.SURFACE, fg=theme.TEXT,
                                   font=(theme.FONT_FAMILY, 10, "bold"), width=14, cursor="hand2")
        self.title_lbl.pack(side="left", expand=True)
        self.title_lbl.bind("<Button-1>", lambda e: self._toggle_month_picker())
        self.title_lbl.bind("<Enter>", lambda e: self.title_lbl.configure(fg=theme.PRIMARY))
        self.title_lbl.bind("<Leave>", lambda e: self.title_lbl.configure(fg=theme.TEXT))
        self.next_btn = tk.Button(header, text="\u203a", command=self._on_next, bd=0,
                                   bg=theme.SURFACE, fg=theme.PRIMARY, activebackground=theme.NEUTRAL_HOVER,
                                   activeforeground=theme.PRIMARY, font=(theme.FONT_FAMILY, 11, "bold"),
                                   cursor="hand2", relief="flat")
        self.next_btn.pack(side="right")

        self.grid_frame = tk.Frame(card, bg=theme.SURFACE)
        self.grid_frame.pack(padx=10, pady=(0, 10))

        for i, d in enumerate(("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")):
            tk.Label(self.grid_frame, text=d, width=3, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                     font=(theme.FONT_FAMILY, 8, "bold")).grid(row=0, column=i, pady=(0, 4))

        self._day_cells = []
        for r in range(1, 7):
            row_cells = []
            for c in range(7):
                lbl = tk.Label(self.grid_frame, text="", width=3, bg=theme.SURFACE,
                                fg=theme.TEXT, font=(theme.FONT_FAMILY, 9), cursor="hand2")
                lbl.grid(row=r, column=c, ipady=3)
                row_cells.append(lbl)
            self._day_cells.append(row_cells)

        # Month-picker view: hidden until the header title is clicked. Lets
        # you jump straight to any month of the shown year instead of
        # clicking prev/next repeatedly.
        self.month_frame = tk.Frame(card, bg=theme.SURFACE)
        self._month_cells = []
        for i in range(12):
            lbl = tk.Label(self.month_frame, text=calendar.month_abbr[i + 1], width=5,
                            bg=theme.SURFACE, fg=theme.TEXT, font=(theme.FONT_FAMILY, 9),
                            cursor="hand2")
            lbl.grid(row=i // 3, column=i % 3, padx=3, pady=3, ipady=6)
            self._month_cells.append(lbl)

        self._render_month()
        self.bind("<Escape>", lambda e: self.destroy())
        # Any click that lands outside this popup closes it, without relying
        # on focus-out (which would also fire, wrongly, when clicking the
        # popup's own prev/next/day widgets).
        self._outside_click_id = master.winfo_toplevel().bind(
            "<Button-1>", self._on_root_click, add="+")
        self.bind("<Destroy>", self._cleanup_binding)
        self.after(10, self.focus_set)

    def _on_root_click(self, event):
        widget = event.widget
        while widget is not None:
            if widget == self:
                return  # click was inside the popup itself
            widget = widget.master
        self.destroy()

    def _cleanup_binding(self, _event):
        try:
            self.master.winfo_toplevel().unbind("<Button-1>", self._outside_click_id)
        except Exception:
            pass

    # ---- header prev/next: month-stepping in day view, year-stepping in
    # the month-picker view, so the same two arrows do the obvious thing ----
    def _on_prev(self):
        if self.mode == "month":
            self.view_year -= 1
            self._render_month_picker()
        else:
            self._prev_month()

    def _on_next(self):
        if self.mode == "month":
            self.view_year += 1
            self._render_month_picker()
        else:
            self._next_month()

    def _toggle_month_picker(self):
        if self.mode == "day":
            self.mode = "month"
            self.grid_frame.pack_forget()
            self._render_month_picker()
            self.month_frame.pack(padx=10, pady=(0, 10))
        else:
            self.mode = "day"
            self.month_frame.pack_forget()
            self._render_month()
            self.grid_frame.pack(padx=10, pady=(0, 10))

    def _render_month_picker(self):
        self.title_lbl.configure(text=str(self.view_year))
        today = date.today()
        for i, lbl in enumerate(self._month_cells):
            month_num = i + 1
            is_current = month_num == self.view_month and self.view_year == self.selected.year
            is_this_month = (self.view_year, month_num) == (today.year, today.month)
            bg = theme.PRIMARY if is_current else (theme.NEUTRAL if is_this_month else theme.SURFACE)
            fg = "white" if is_current else theme.TEXT
            lbl.configure(bg=bg, fg=fg)
            lbl.unbind("<Button-1>")
            lbl.unbind("<Enter>")
            lbl.unbind("<Leave>")
            lbl.bind("<Button-1>", lambda e, m=month_num: self._pick_month(m))
            if not is_current:
                lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=theme.NEUTRAL_HOVER))
                lbl.bind("<Leave>", lambda e, w=lbl, b=bg: w.configure(bg=b))

    def _pick_month(self, month_num):
        self.view_month = month_num
        self.mode = "day"
        self.month_frame.pack_forget()
        self._render_month()
        self.grid_frame.pack(padx=10, pady=(0, 10))

    def _prev_month(self):
        self.view_month -= 1
        if self.view_month == 0:
            self.view_month = 12
            self.view_year -= 1
        self._render_month()

    def _next_month(self):
        self.view_month += 1
        if self.view_month == 13:
            self.view_month = 1
            self.view_year += 1
        self._render_month()

    def _render_month(self):
        self.title_lbl.configure(text=f"{calendar.month_name[self.view_month]} {self.view_year}")
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.view_year, self.view_month)
        today = date.today()
        for r in range(6):
            week = weeks[r] if r < len(weeks) else [0] * 7
            for c in range(7):
                day = week[c]
                lbl = self._day_cells[r][c]
                lbl.unbind("<Button-1>")
                lbl.unbind("<Enter>")
                lbl.unbind("<Leave>")
                if day == 0:
                    lbl.configure(text="", bg=theme.SURFACE)
                    continue
                this_date = date(self.view_year, self.view_month, day)
                is_today = this_date == today
                is_selected = this_date == self.selected
                bg = theme.PRIMARY if is_selected else (theme.NEUTRAL if is_today else theme.SURFACE)
                fg = "white" if is_selected else theme.TEXT
                lbl.configure(text=str(day), bg=bg, fg=fg)
                lbl.bind("<Button-1>", lambda e, d=this_date: self._pick(d))
                if not is_selected:
                    lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=theme.NEUTRAL_HOVER))
                    lbl.bind("<Leave>", lambda e, w=lbl, b=bg: w.configure(bg=b))

    def _pick(self, picked_date):
        self.on_pick(picked_date)
        self.destroy()


class DateEntry(ttk.Frame):
    """
    Compact date input used everywhere a date needs to be typed: as the
    digits go in, the '-' separators fill themselves in automatically
    (order='ymd' -> YYYY-MM-DD, order='dmy' -> DD-MM-YYYY). Clicking the
    calendar icon opens a small popup month-view to pick a date instead of
    typing at all.

    Exposes the same get()/delete()/insert() surface as a plain ttk.Entry,
    so existing call sites only need to change how the widget is built, not
    how it's read from or pre-filled.
    """

    _SEGMENTS = {"ymd": (4, 2, 2), "dmy": (2, 2, 4)}

    def __init__(self, master, order="ymd", width=12, **entry_kwargs):
        super().__init__(master)
        self.order = order
        self._segments = self._SEGMENTS[order]
        self._max_digits = sum(self._segments)
        self._digits = ""

        self.entry = ttk.Entry(self, width=width, **entry_kwargs)
        self.entry.pack(side="left")
        self.entry.bind("<Key>", self._on_key)

        ttk.Button(self, text="\U0001F4C5", width=3, style="Ghost.TButton",
                   command=self._open_calendar).pack(side="left", padx=(4, 0))

    # ---- ttk.Entry-like public API -----------------------------------------
    def get(self):
        return self.entry.get()

    def delete(self, first, last=None):
        self.entry.delete(first, last if last is not None else tk.END)
        self._digits = ""

    def insert(self, index, s):
        self._digits = "".join(ch for ch in str(s) if ch.isdigit())[:self._max_digits]
        self._render()

    def focus_set(self):
        self.entry.focus_set()

    # ---- typing behaviour: digits only, dashes are automatic ----------------
    def _on_key(self, event):
        if event.keysym in ("Tab", "ISO_Left_Tab"):
            return None  # let focus traversal through untouched
        if event.keysym in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return None  # modifier presses by themselves aren't text input
        if event.keysym in ("BackSpace", "Delete"):
            self._digits = self._digits[:-1]
            self._render()
            return "break"
        if event.char.isdigit() and len(self._digits) < self._max_digits:
            self._digits += event.char
            self._render()
        return "break"  # only digits/backspace ever change the field's text

    def _render(self):
        parts, idx = [], 0
        for seg_len in self._segments:
            seg = self._digits[idx:idx + seg_len]
            idx += seg_len
            if seg:
                parts.append(seg)
        self.entry.delete(0, tk.END)
        self.entry.insert(0, "-".join(parts))
        self.entry.icursor(tk.END)

    # ---- calendar popup -----------------------------------------------------
    def _open_calendar(self):
        initial = self._parse_current() or date.today()
        popup = _CalendarPopup(self, on_pick=self._on_date_picked, initial=initial)
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        popup.geometry(f"+{x}+{y}")

    def _on_date_picked(self, picked_date):
        if self.order == "ymd":
            digits = f"{picked_date.year:04d}{picked_date.month:02d}{picked_date.day:02d}"
        else:
            digits = f"{picked_date.day:02d}{picked_date.month:02d}{picked_date.year:04d}"
        self._digits = digits
        self._render()

    def _parse_current(self):
        digits = self._digits
        if len(digits) != self._max_digits:
            return None
        try:
            if self.order == "ymd":
                return date(int(digits[0:4]), int(digits[4:6]), int(digits[6:8]))
            return date(int(digits[4:8]), int(digits[2:4]), int(digits[0:2]))
        except ValueError:
            return None


# ==========================================================================
# Scrollable container (Canvas + Scrollbar), used to let the timeline below
# scroll within a fixed height instead of stretching the whole page.
# ==========================================================================
class ScrollableFrame(tk.Frame):
    """A vertically scrollable container. Put child widgets inside `.body`
    (not the ScrollableFrame itself). Pass a pixel `height` for a fixed-size
    panel (e.g. the booking timeline), or leave it as None to have the
    canvas fill whatever space `.pack(fill="both", expand=True)` gives it -
    used for a whole page's worth of content so it scrolls instead of being
    clipped when a window is too short to show everything at once."""

    def __init__(self, parent, height=None, bg=None):
        bg = bg or theme.SURFACE
        super().__init__(parent, bg=bg)
        canvas_kwargs = {"bg": bg, "highlightthickness": 0}
        if height is not None:
            canvas_kwargs["height"] = height
        self.canvas = tk.Canvas(self, **canvas_kwargs)
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._on_body_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", lambda e: self._bind_wheel())
        self.canvas.bind("<Leave>", lambda e: self._unbind_wheel())
        self.canvas.bind("<Destroy>", lambda e: self._unbind_wheel())

    def _on_body_configure(self, _event):
        try:
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        except Exception:
            pass

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfigure(self._window, width=event.width)
        except Exception:
            pass

    def _bind_wheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.canvas.bind_all("<Button-4>", self._on_wheel)
        self.canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind_wheel(self):
        try:
            self.canvas.unbind_all("<MouseWheel>")
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_wheel(self, event):
        try:
            if getattr(event, "num", None) == 4:
                self.canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass


# ==========================================================================
# Big, always-visible month calendar for the "click a date" booking flow
# (as opposed to _CalendarPopup, which is a small popup anchored to a
# DateEntry's calendar button). Past dates aren't selectable - you can't
# book a facility yesterday.
# ==========================================================================
class BigCalendar(tk.Frame):
    """An embedded month calendar. Click a day to pick it; `on_pick(date)`
    fires with the chosen `datetime.date`. Optionally mark specific dates
    with a small dot via `set_marked_dates()`, e.g. days you already have a
    booking on."""

    def __init__(self, parent, on_pick=None, initial=None):
        super().__init__(parent, bg=theme.SURFACE)
        self.on_pick = on_pick
        today = date.today()
        initial = initial or today
        self.view_year = initial.year
        self.view_month = initial.month
        self.selected = initial
        self._marked = set()

        header = tk.Frame(self, bg=theme.SURFACE)
        header.pack(fill="x", pady=(0, 6))
        tk.Button(header, text="\u2039", command=self._prev_month, bd=0, bg=theme.SURFACE,
                  fg=theme.PRIMARY, activebackground=theme.NEUTRAL_HOVER, activeforeground=theme.PRIMARY,
                  font=(theme.FONT_FAMILY, 13, "bold"), cursor="hand2", relief="flat").pack(side="left")
        self.title_lbl = tk.Label(header, text="", bg=theme.SURFACE, fg=theme.TEXT,
                                   font=(theme.FONT_FAMILY, 11, "bold"), width=16)
        self.title_lbl.pack(side="left", expand=True)
        tk.Button(header, text="\u203a", command=self._next_month, bd=0, bg=theme.SURFACE,
                  fg=theme.PRIMARY, activebackground=theme.NEUTRAL_HOVER, activeforeground=theme.PRIMARY,
                  font=(theme.FONT_FAMILY, 13, "bold"), cursor="hand2", relief="flat").pack(side="right")

        grid = tk.Frame(self, bg=theme.SURFACE)
        grid.pack()
        for i, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            tk.Label(grid, text=d, width=4, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                     font=(theme.FONT_FAMILY, 8, "bold")).grid(row=0, column=i, pady=(0, 6))

        self._day_cells = []
        for r in range(1, 7):
            row_cells = []
            for c in range(7):
                lbl = tk.Label(grid, text="", width=4, bg=theme.SURFACE, fg=theme.TEXT,
                                font=(theme.FONT_FAMILY, 10), cursor="hand2")
                lbl.grid(row=r, column=c, ipady=8, padx=1, pady=1)
                row_cells.append(lbl)
            self._day_cells.append(row_cells)

        self._render()

    def get_selected(self):
        return self.selected

    def set_selected(self, picked_date):
        self.selected = picked_date
        self.view_year, self.view_month = picked_date.year, picked_date.month
        self._render()

    def set_marked_dates(self, dates_iterable):
        self._marked = set(dates_iterable)
        self._render()

    def _prev_month(self):
        self.view_month -= 1
        if self.view_month == 0:
            self.view_month, self.view_year = 12, self.view_year - 1
        self._render()

    def _next_month(self):
        self.view_month += 1
        if self.view_month == 13:
            self.view_month, self.view_year = 1, self.view_year + 1
        self._render()

    def _render(self):
        self.title_lbl.configure(text=f"{calendar.month_name[self.view_month]} {self.view_year}")
        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(self.view_year, self.view_month)
        today = date.today()
        for r in range(6):
            week = weeks[r] if r < len(weeks) else [0] * 7
            for c in range(7):
                day = week[c]
                lbl = self._day_cells[r][c]
                lbl.unbind("<Button-1>")
                lbl.unbind("<Enter>")
                lbl.unbind("<Leave>")
                if day == 0:
                    lbl.configure(text="", bg=theme.SURFACE)
                    continue
                this_date = date(self.view_year, self.view_month, day)
                is_past = this_date < today
                is_selected = this_date == self.selected
                is_today = this_date == today
                marker = "\u2022" if this_date in self._marked else ""
                bg = theme.PRIMARY if is_selected else (theme.NEUTRAL if is_today else theme.SURFACE)
                fg = "white" if is_selected else (theme.MUTED_TEXT if is_past else theme.TEXT)
                lbl.configure(text=f"{day}\n{marker}" if marker else str(day), bg=bg, fg=fg,
                              cursor="hand2" if not is_past else "arrow")
                if not is_past:
                    lbl.bind("<Button-1>", lambda e, d=this_date: self._pick(d))
                    if not is_selected:
                        lbl.bind("<Enter>", lambda e, w=lbl: w.configure(bg=theme.NEUTRAL_HOVER))
                        lbl.bind("<Leave>", lambda e, w=lbl, b=bg: w.configure(bg=b))

    def _pick(self, picked_date):
        self.selected = picked_date
        self._render()
        if self.on_pick:
            self.on_pick(picked_date)


# ==========================================================================
# Click-to-book time slot timeline - the "click click, done" alternative to
# typing start/end times by hand. Click a free slot to start a range, click
# another free slot to finish it (everything in between must also be free);
# hovering after picking a start previews the range before you commit to it.
# ==========================================================================
class TimeSlotTimeline(tk.Frame):
    SLOT_MINUTES = 30

    def __init__(self, parent, start_hour=7, end_hour=22, on_range_pick=None, height=300):
        super().__init__(parent, bg=theme.SURFACE)
        self.start_hour = start_hour
        self.end_hour = end_hour
        self.on_range_pick = on_range_pick
        self._booked = set()
        self._range_start = None
        self._range_end = None

        self.scroller = ScrollableFrame(self, height=height)
        self.scroller.pack(fill="both", expand=True)
        self._buttons = {}
        self._slots = []
        self._build_slots()

    def _build_slots(self):
        for w in self.scroller.body.winfo_children():
            w.destroy()
        self._buttons = {}
        self._slots = []
        t = self.start_hour * 60
        end = self.end_hour * 60
        while t < end:
            hh, mm = divmod(t, 60)
            self._slots.append(f"{hh:02d}:{mm:02d}")
            t += self.SLOT_MINUTES

        for i, slot in enumerate(self._slots):
            end_label = self._add_minutes(slot, self.SLOT_MINUTES)
            btn = tk.Label(self.scroller.body, text=f"{slot} \u2013 {end_label}",
                            bg=theme.SURFACE, fg=theme.TEXT, font=(theme.FONT_FAMILY, 9),
                            anchor="w", padx=10, pady=7, cursor="hand2")
            btn.pack(fill="x", pady=1)
            btn.bind("<Button-1>", lambda e, s=slot: self._on_click(s))
            btn.bind("<Enter>", lambda e, s=slot: self._on_hover(s))
            self._buttons[slot] = btn
        self._repaint()

    def set_booked(self, ranges):
        """`ranges`: iterable of (start 'HH:MM', end 'HH:MM') spans already
        taken - every slot they touch is shown as booked and unclickable."""
        booked = set()
        for s, e in ranges:
            t = (self._to_minutes(s) // self.SLOT_MINUTES) * self.SLOT_MINUTES
            te = self._to_minutes(e)
            while t < te:
                hh, mm = divmod(t, 60)
                booked.add(f"{hh:02d}:{mm:02d}")
                t += self.SLOT_MINUTES
        self._booked = booked
        self._range_start = None
        self._range_end = None
        self._repaint()

    def clear_selection(self):
        self._range_start = None
        self._range_end = None
        self._repaint()

    def get_range(self):
        if self._range_start and self._range_end:
            return self._range_start, self._add_minutes(self._range_end, self.SLOT_MINUTES)
        return None, None

    def set_range(self, start, end):
        """Programmatically pre-select a range, e.g. to seed the timeline with
        an existing booking's current time when rescheduling. `start`/`end`
        use the same 'HH:MM' format returned by `get_range()` (end exclusive)."""
        if not (start and end):
            return
        self._range_start = start
        self._range_end = self._add_minutes(end, -self.SLOT_MINUTES)
        self._repaint()

    def _on_click(self, slot):
        if slot in self._booked:
            return
        if self._range_start is None or (self._range_start and self._range_end):
            self._range_start, self._range_end = slot, None
        else:
            lo, hi = sorted((self._range_start, slot), key=self._to_minutes)
            if self._span_is_free(lo, hi):
                self._range_start, self._range_end = lo, hi
                if self.on_range_pick:
                    s, e = self.get_range()
                    self.on_range_pick(s, e)
            else:
                self._range_start, self._range_end = slot, None
        self._repaint()

    def _on_hover(self, slot):
        if self._range_start and not self._range_end:
            self._repaint(preview=slot)

    def _span_is_free(self, lo, hi):
        t = self._to_minutes(lo)
        end = self._to_minutes(hi)
        while t <= end:
            hh, mm = divmod(t, 60)
            if f"{hh:02d}:{mm:02d}" in self._booked:
                return False
            t += self.SLOT_MINUTES
        return True

    def _span_set(self, lo, hi):
        out = set()
        t = self._to_minutes(lo)
        end = self._to_minutes(hi)
        while t <= end:
            hh, mm = divmod(t, 60)
            out.add(f"{hh:02d}:{mm:02d}")
            t += self.SLOT_MINUTES
        return out

    def _repaint(self, preview=None):
        preview_range = set()
        if preview and self._range_start and not self._range_end:
            lo, hi = sorted((self._range_start, preview), key=self._to_minutes)
            if self._span_is_free(lo, hi):
                preview_range = self._span_set(lo, hi)

        picked_range = self._span_set(self._range_start, self._range_end) \
            if (self._range_start and self._range_end) else set()

        for slot, btn in self._buttons.items():
            if slot in self._booked:
                btn.configure(bg=theme.NEUTRAL, fg=theme.MUTED_TEXT, cursor="arrow")
            elif slot in picked_range or slot == self._range_start:
                btn.configure(bg=theme.PRIMARY, fg="white", cursor="hand2")
            elif slot in preview_range:
                btn.configure(bg=theme.PRIMARY_SOFT, fg=theme.PRIMARY, cursor="hand2")
            else:
                btn.configure(bg=theme.SURFACE, fg=theme.TEXT, cursor="hand2")

    @staticmethod
    def _to_minutes(hhmm):
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    @staticmethod
    def _add_minutes(hhmm, delta):
        total = TimeSlotTimeline._to_minutes(hhmm) + delta
        h, m = divmod(total, 60)
        return f"{h:02d}:{m:02d}"


# ==========================================================================
# Combined "pick a date, then click a time slot" widget - the same click-to-
# book flow the student booking form uses, packaged up so every other place
# in the app that needs a booking date/time (new bookings, reschedules) can
# reuse it instead of asking people to type dates and times by hand.
# ==========================================================================
class DateTimeRangePicker(tk.Frame):
    """`BigCalendar` + `TimeSlotTimeline` bundled together with a legend and
    a "Selected: ..." status line. Optionally pre-seeded with an existing
    date/time (for rescheduling) and hooked up to a `booked_provider`
    callback that supplies already-taken ranges for whichever date is
    currently selected, so double-bookings are visible before you submit."""

    def __init__(self, parent, on_change=None, initial_date=None,
                 initial_start=None, initial_end=None,
                 start_hour=7, end_hour=22, timeline_height=260):
        super().__init__(parent, bg=theme.SURFACE)
        self.on_change = on_change
        self._booked_provider = None
        self._pending_initial = (initial_start, initial_end) if (initial_start and initial_end) else None

        steps = tk.Frame(self, bg=theme.SURFACE)
        steps.pack(fill="both", expand=True)

        cal_col = tk.Frame(steps, bg=theme.SURFACE)
        cal_col.pack(side="left", padx=(0, 20), anchor="n")
        tk.Label(cal_col, text="1. Pick a date", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 6))
        self.calendar = BigCalendar(cal_col, on_pick=self._on_date_pick, initial=initial_date)
        self.calendar.pack()

        time_col = tk.Frame(steps, bg=theme.SURFACE)
        time_col.pack(side="left", fill="both", expand=True)
        tk.Label(time_col, text="2. Pick a time \u2014 click a slot, then click again to set the end",
                 bg=theme.SURFACE, fg=theme.TEXT, font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 6))

        legend = tk.Frame(time_col, bg=theme.SURFACE)
        legend.pack(anchor="w", pady=(0, 6))
        for color, text in ((theme.SURFACE, "Available"), (theme.PRIMARY, "Selected"), (theme.NEUTRAL, "Booked")):
            sw = tk.Frame(legend, bg=color, width=12, height=12, highlightthickness=1,
                          highlightbackground=theme.BORDER, highlightcolor=theme.BORDER)
            sw.pack(side="left", padx=(0, 4))
            sw.pack_propagate(False)
            tk.Label(legend, text=text, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                     font=(theme.FONT_FAMILY, 8)).pack(side="left", padx=(0, 12))

        self.timeline = TimeSlotTimeline(time_col, start_hour=start_hour, end_hour=end_hour,
                                          on_range_pick=lambda s, e: self._notify(),
                                          height=timeline_height)
        self.timeline.pack(fill="both", expand=True)

        self.selection_lbl = tk.Label(self, text="Select a date and time above to continue.",
                                       bg=theme.SURFACE, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9))
        self.selection_lbl.pack(anchor="w", pady=(10, 0))

    def set_booked_provider(self, fn):
        """`fn(date_iso_str) -> [(start, end), ...]` of ranges already taken
        for that date. Called once immediately and again every time the
        selected date changes."""
        self._booked_provider = fn
        self.refresh_booked()

    def refresh_booked(self):
        if not self._booked_provider:
            return
        target_date = self.calendar.get_selected().isoformat()
        ranges = self._booked_provider(target_date)
        self.timeline.set_booked(ranges)  # clears any existing selection
        if self._pending_initial:
            s, e = self._pending_initial
            self._pending_initial = None
            self.timeline.set_range(s, e)
        self._notify()

    def _on_date_pick(self, _picked_date):
        self.refresh_booked()

    def _notify(self):
        s, e = self.timeline.get_range()
        if s and e:
            d = self.calendar.get_selected()
            self.selection_lbl.configure(
                text=f"Selected: {d.strftime('%a, %d %b %Y')}  \u2022  {s} \u2013 {e}",
                fg=theme.PRIMARY)
        else:
            self.selection_lbl.configure(text="Select a date and time above to continue.",
                                          fg=theme.MUTED_TEXT)
        if self.on_change:
            self.on_change()

    def get_selection(self):
        """Returns (date_iso, start, end); start/end are None if no time slot
        has been picked yet."""
        s, e = self.timeline.get_range()
        return self.calendar.get_selected().isoformat(), s, e


# ==========================================================================
# Rounded, hover-aware button (ttk buttons can't do real rounded corners)
# ==========================================================================
def _rounded_points(x1, y1, x2, y2, r):
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _button_palette(style):
    """Looked up fresh on every button creation (rather than cached once at
    import time) so buttons pick up the current light/dark palette."""
    palettes = {
        "primary": (theme.PRIMARY, theme.PRIMARY_HOVER, theme.PRIMARY_PRESSED, "white"),
        "success": (theme.SUCCESS, theme.SUCCESS_HOVER, "#0f6e3f", "white"),
        "danger": (theme.DANGER, theme.DANGER_HOVER, "#932b25", "white"),
        "neutral": (theme.NEUTRAL, theme.NEUTRAL_HOVER, theme.ROW_SELECT, theme.TEXT),
        "ghost": (theme.SURFACE, theme.NEUTRAL, theme.NEUTRAL_HOVER, theme.PRIMARY),
    }
    return palettes.get(style, palettes["primary"])


class RoundedButton(tk.Canvas):
    """A pill-shaped button drawn on a Canvas, with real hover/press colour states."""

    def __init__(self, parent, text, command=None, style="primary",
                 container_bg=None, radius=16, padx=20, pady=10,
                 font=None, width=None, circle=False):
        self.bg_color, self.hover_color, self.press_color, self.fg_color = \
            _button_palette(style)
        self.command = command
        self.text = text
        self.radius = radius
        self._font = font or tkfont.Font(family=theme.FONT_FAMILY, size=10, weight="bold")
        container_bg = container_bg or theme.BG

        text_w = self._font.measure(text)
        text_h = self._font.metrics("linespace")
        w = width or (text_w + padx * 2)
        h = text_h + pady * 2
        if circle:
            w = h = max(w, h)
            self.radius = w / 2

        super().__init__(parent, width=w, height=h, highlightthickness=0,
                          bg=container_bg, bd=0, cursor="hand2")
        self._w, self._h = w, h
        self._draw(self.bg_color)

        self.bind("<Enter>", lambda e: self._draw(self.hover_color))
        self.bind("<Leave>", lambda e: self._draw(self.bg_color))
        self.bind("<ButtonPress-1>", lambda e: self._draw(self.press_color))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _draw(self, color):
        self.delete("all")
        pts = _rounded_points(1, 1, self._w - 1, self._h - 1, self.radius)
        self.create_polygon(pts, smooth=True, fill=color, outline=color)
        self.create_text(self._w / 2, self._h / 2, text=self.text,
                          fill=self.fg_color, font=self._font)

    def _on_release(self, event):
        self._draw(self.hover_color)
        inside = 0 <= event.x <= self._w and 0 <= event.y <= self._h
        if inside and self.command:
            self.command()

    def set_text(self, text):
        self.text = text
        self._draw(self.bg_color)


# ==========================================================================
# Image carousel / slider
# ==========================================================================
class ImageCarousel(ttk.Frame):
    def __init__(self, master, width=620, height=320, autoplay_ms=4500, on_select=None):
        super().__init__(master, style="Surface.TFrame")
        self.disp_w = width
        self.disp_h = height
        self.autoplay_ms = autoplay_ms
        self.on_select = on_select

        self._paths = []
        self._captions = []
        self._index = 0
        self._photo = None
        self._after_id = None
        self._paused = False

        outer = ttk.Frame(self, style="Surface.TFrame")
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        row = ttk.Frame(outer, style="Surface.TFrame")
        row.pack(fill="both", expand=True)

        self.prev_btn = ttk.Button(row, text="\u2039", width=3, style="Nav.TButton",
                                    command=self.show_prev)
        self.prev_btn.pack(side="left", fill="y")

        self.canvas = tk.Canvas(row, width=self.disp_w, height=self.disp_h,
                                 highlightthickness=0, bg=theme.SURFACE, cursor="hand2")
        self.canvas.pack(side="left", padx=6, pady=6)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Enter>", lambda e: self._set_paused(True))
        self.canvas.bind("<Leave>", lambda e: self._set_paused(False))

        self.next_btn = ttk.Button(row, text="\u203a", width=3, style="Nav.TButton",
                                    command=self.show_next)
        self.next_btn.pack(side="left", fill="y")

        self.dots_frame = ttk.Frame(outer, style="Surface.TFrame")
        self.dots_frame.pack(pady=(0, 8))

        self._placeholder_text_id = None

    # ---- public API ----------------------------------------------------
    def set_slides(self, paths, captions=None):
        """Replace the slide list. `paths` is a list of image file paths."""
        keep_index = self._index if paths and len(paths) == len(self._paths) else 0
        self._paths = list(paths)
        self._captions = list(captions) if captions else [""] * len(self._paths)
        self._index = min(keep_index, max(len(self._paths) - 1, 0))
        self._rebuild_dots()
        self._render()
        self._restart_autoplay()

    def show_prev(self):
        if not self._paths:
            return
        self._index = (self._index - 1) % len(self._paths)
        self._render()
        self._restart_autoplay()

    def show_next(self):
        if not self._paths:
            return
        self._index = (self._index + 1) % len(self._paths)
        self._render()
        self._restart_autoplay()

    def go_to(self, index):
        if not self._paths:
            return
        self._index = index % len(self._paths)
        self._render()
        self._restart_autoplay()

    def destroy(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        super().destroy()

    # ---- internals -------------------------------------------------------
    def _set_paused(self, paused):
        self._paused = paused

    def _on_click(self, _event):
        if self.on_select and self._paths:
            self.on_select(self._index)

    def _rebuild_dots(self):
        for w in self.dots_frame.winfo_children():
            w.destroy()
        self._dot_labels = []
        for i in range(len(self._paths)):
            dot = tk.Label(self.dots_frame, text="\u25CF", font=("Segoe UI", 9),
                            bg=theme.SURFACE, fg=theme.BORDER, cursor="hand2")
            dot.pack(side="left", padx=3)
            dot.bind("<Button-1>", lambda e, idx=i: self.go_to(idx))
            self._dot_labels.append(dot)

    def _update_dots(self):
        for i, dot in enumerate(getattr(self, "_dot_labels", [])):
            dot.configure(fg=theme.PRIMARY if i == self._index else theme.BORDER)

    def _render(self):
        self.canvas.delete("all")
        if not self._paths:
            self.canvas.create_rectangle(0, 0, self.disp_w, self.disp_h,
                                          fill=theme.NEUTRAL, outline="")
            self.canvas.create_text(self.disp_w / 2, self.disp_h / 2,
                                     text="No facilities to display",
                                     fill=theme.MUTED_TEXT, font=("Segoe UI", 12, "bold"))
            return
        path = self._paths[self._index]
        try:
            img = Image.open(path)
            img = img.resize((self.disp_w, self.disp_h), Image.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        except Exception:
            self.canvas.create_rectangle(0, 0, self.disp_w, self.disp_h,
                                          fill=theme.NEUTRAL, outline="")
            self.canvas.create_text(self.disp_w / 2, self.disp_h / 2,
                                     text="Image unavailable", fill=theme.MUTED_TEXT)
        caption = self._captions[self._index] if self._index < len(self._captions) else ""
        if caption:
            self.canvas.create_text(10, self.disp_h - 12, anchor="w", text=caption,
                                     fill="white", font=("Segoe UI", 8))
        self._update_dots()

    def _restart_autoplay(self):
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        if self.autoplay_ms and len(self._paths) > 1:
            self._after_id = self.after(self.autoplay_ms, self._auto_advance)

    def _auto_advance(self):
        if not self._paused and self._paths:
            self._index = (self._index + 1) % len(self._paths)
            self._render()
        self._after_id = self.after(self.autoplay_ms, self._auto_advance)


# ==========================================================================
# Treeview row hover highlight
# ==========================================================================
def attach_row_hover(tree, hover_tag="hoverrow"):
    """
    Adds a live highlight to the row under the mouse. Keeps whatever other
    tags a row already has (status colours, alternating stripes) and only
    swaps in the hover background while the cursor is over that row.
    """
    state = {"current": None, "backup": None}

    def on_motion(event):
        row = tree.identify_row(event.y)
        if row == state["current"]:
            return
        _restore(tree, state)
        if row:
            state["current"] = row
            state["backup"] = tree.item(row, "tags")
            new_tags = tuple(t for t in state["backup"] if t != hover_tag) + (hover_tag,)
            tree.item(row, tags=new_tags)

    def on_leave(_event):
        _restore(tree, state)

    tree.bind("<Motion>", on_motion, add="+")
    tree.bind("<Leave>", on_leave, add="+")


def _restore(tree, state):
    if state["current"] is not None:
        try:
            if tree.exists(state["current"]):
                tree.item(state["current"], tags=state["backup"])
        except Exception:
            pass
        state["current"] = None
        state["backup"] = None


def restripe(tree, iids=None):
    """Re-applies alternating oddrow/evenrow tags (call after any refresh)."""
    children = iids if iids is not None else tree.get_children()
    for i, iid in enumerate(children):
        existing = [t for t in tree.item(iid, "tags") if t not in ("oddrow", "evenrow")]
        stripe = "oddrow" if i % 2 else "evenrow"
        tree.item(iid, tags=tuple(existing) + (stripe,))


def page_header(parent, title, subtitle=None):
    """Consistent page title + optional subtitle + thin accent divider."""
    wrap = tk.Frame(parent, bg=theme.BG)
    wrap.pack(fill="x", pady=(0, 14))
    tk.Label(wrap, text=title, bg=theme.BG, fg=theme.TEXT,
              font=(theme.FONT_FAMILY, 19, "bold")).pack(anchor="w")
    if subtitle:
        tk.Label(wrap, text=subtitle, bg=theme.BG, fg=theme.MUTED_TEXT,
                  font=(theme.FONT_FAMILY, 10)).pack(anchor="w", pady=(2, 8))
    else:
        tk.Frame(wrap, height=8, bg=theme.BG).pack()
    tk.Frame(wrap, bg=theme.PRIMARY, height=3).pack(fill="x", pady=(2, 0))
    return wrap


# ==========================================================================
# Soft "elevated card" illusion using plain nested frames (no canvas maths,
# so it can't misrender regardless of platform/theme quirks).
# ==========================================================================
def shadow_wrap(parent, bg_behind=None):
    """
    Returns (outer, card) where `outer` is a thin frame coloured like a soft
    shadow and `card` is the actual white surface sitting on top of it,
    offset by a couple of pixels so a sliver of shadow shows on the
    bottom-right edge. Pack/grid `outer`, then put content inside `card`.
    """
    bg_behind = bg_behind or theme.BG
    outer = tk.Frame(parent, bg=theme.SHADOW)
    card = tk.Frame(outer, bg=theme.SURFACE, highlightthickness=1,
                     highlightbackground=theme.BORDER, highlightcolor=theme.BORDER)
    card.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
    return outer, card


# ==========================================================================
# Stat card (dashboard tiles): icon chip + big value + caption, on a soft card
# ==========================================================================
class StatCard(tk.Frame):
    """
    A dashboard stat tile. Construct it, then place it on screen via its
    `.outer` attribute (the shadowed wrapper), e.g. `card.outer.grid(...)`.
    """
    def __init__(self, master, icon, value, label, accent=None):
        accent = accent or theme.PRIMARY
        self.outer = tk.Frame(master, bg=theme.SHADOW)
        super().__init__(self.outer, bg=theme.SURFACE, highlightthickness=1,
                          highlightbackground=theme.BORDER, highlightcolor=theme.BORDER)
        tk.Frame.pack(self, fill="both", expand=True, padx=(0, 3), pady=(0, 3))

        pad = tk.Frame(self, bg=theme.SURFACE)
        pad.pack(fill="both", expand=True, padx=18, pady=16)

        chip = tk.Canvas(pad, width=46, height=46, highlightthickness=0, bg=theme.SURFACE)
        chip.pack(anchor="w")
        chip.create_oval(1, 1, 45, 45, fill=accent, outline="")
        chip.create_text(23, 23, text=icon, font=("Segoe UI Emoji", 17), fill="white")

        self.value_label = tk.Label(pad, text=str(value), bg=theme.SURFACE, fg=theme.TEXT,
                                     font=(theme.FONT_FAMILY, 23, "bold"))
        self.value_label.pack(anchor="w", pady=(12, 0))
        tk.Label(pad, text=label, bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                  font=(theme.FONT_FAMILY, 9)).pack(anchor="w")


# ==========================================================================
# Sidebar navigation item (plain tk widgets => reliable hover without ttk
# style-map edge cases inside a custom-coloured sidebar)
# ==========================================================================
class NavItem(tk.Frame):
    def __init__(self, master, icon, text, command):
        super().__init__(master, bg=theme.SIDEBAR_BG, cursor="hand2")
        self.command = command
        self._active = False

        self.accent = tk.Frame(self, bg=theme.SIDEBAR_BG, width=4)
        self.accent.pack(side="left", fill="y")

        inner = tk.Frame(self, bg=theme.SIDEBAR_BG)
        inner.pack(side="left", fill="both", expand=True, padx=(10, 4), pady=9)

        self.icon_label = tk.Label(inner, text=icon, bg=theme.SIDEBAR_BG,
                                    font=("Segoe UI Emoji", 12), fg=theme.SIDEBAR_TEXT)
        self.icon_label.pack(side="left")
        self.text_label = tk.Label(inner, text=text, bg=theme.SIDEBAR_BG, fg=theme.SIDEBAR_TEXT,
                                    font=(theme.FONT_FAMILY, 10, "bold"), anchor="w")
        self.text_label.pack(side="left", padx=(10, 0), fill="x", expand=True)

        self._widgets = [self, inner, self.icon_label, self.text_label]
        for w in self._widgets:
            w.bind("<Button-1>", lambda e: self.command())
            w.bind("<Enter>", lambda e: self._on_enter())
            w.bind("<Leave>", lambda e: self._on_leave())

    def _on_enter(self):
        if not self._active:
            self._paint(theme.SIDEBAR_BG_HOVER)

    def _on_leave(self):
        if not self._active:
            self._paint(theme.SIDEBAR_BG)

    def _paint(self, bg):
        for w in (self, self.icon_label, self.text_label):
            w.configure(bg=bg)
        for child in self.winfo_children():
            if isinstance(child, tk.Frame) and child is not self.accent:
                child.configure(bg=bg)

    def set_active(self, active):
        self._active = active
        if active:
            self._paint(theme.SIDEBAR_BG_ACTIVE)
            self.accent.configure(bg=theme.SIDEBAR_ACCENT)
            self.text_label.configure(fg="white")
        else:
            self._paint(theme.SIDEBAR_BG)
            self.accent.configure(bg=theme.SIDEBAR_BG)
            self.text_label.configure(fg=theme.SIDEBAR_TEXT)


# ==========================================================================
# Light / dark mode switch - a small pill-shaped toggle with a sliding sun/
# moon knob, drawn on a Canvas so it can have a real handle animation
# instead of relying on a checkbox.
# ==========================================================================
class ThemeToggle(tk.Canvas):
    """
    Click to flip between light and dark mode. `command(is_dark)` is called
    with the *new* state right after the switch animates. The widget only
    updates its own drawing - it's up to the caller to actually re-theme the
    app (see `theme.set_mode` / `FacilityBookingApp._on_theme_toggle`).
    """

    STEPS = 8

    def __init__(self, parent, is_dark=False, command=None, container_bg=None,
                 width=52, height=26):
        self.command = command
        self.is_dark = is_dark
        self.w, self.h = width, height
        self._container_bg = container_bg or theme.BG
        self._animating = False

        super().__init__(parent, width=width, height=height, highlightthickness=0,
                          bg=self._container_bg, bd=0, cursor="hand2")

        r = height / 2 - 2
        self._knob_r = r
        self._knob_min_x = height / 2
        self._knob_max_x = width - height / 2
        self._knob_x = self._knob_max_x if is_dark else self._knob_min_x

        self._draw()
        self.bind("<Button-1>", self._on_click)

    # ---- drawing -----------------------------------------------------------
    def _draw(self):
        self.delete("all")
        track_color = theme.PRIMARY if self.is_dark else theme.BORDER
        pts = _rounded_points(1, 1, self.w - 1, self.h - 1, self.h / 2 - 1)
        self.create_polygon(pts, smooth=True, fill=track_color, outline=track_color)

        r = self._knob_r
        x = self._knob_x
        self.create_oval(x - r, self.h / 2 - r, x + r, self.h / 2 + r,
                          fill="white", outline="")
        icon = "\u263E" if self.is_dark else "\u2600"  # moon / sun
        self.create_text(x, self.h / 2, text=icon, font=("Segoe UI Emoji", int(r)),
                          fill=track_color)

    # ---- interaction ---------------------------------------------------
    def _on_click(self, _event):
        if self._animating:
            return
        self.is_dark = not self.is_dark
        self._animate_to(self._knob_max_x if self.is_dark else self._knob_min_x)

    def _animate_to(self, target_x, step=0):
        self._animating = True
        start_x = self._knob_x
        distance = target_x - start_x
        if step >= self.STEPS or distance == 0:
            self._knob_x = target_x
            self._draw()
            self._animating = False
            if self.command:
                self.command(self.is_dark)
            return
        self._knob_x = start_x + distance * (step + 1) / self.STEPS
        self._draw()
        self.after(12, lambda: self._animate_to(target_x, step + 1))

    def set_state(self, is_dark, redraw_bg=None):
        """Snap to a state without animating or firing the callback - used
        right after a rebuild so a fresh toggle reflects the current mode."""
        self.is_dark = is_dark
        if redraw_bg is not None:
            self._container_bg = redraw_bg
            self.configure(bg=redraw_bg)
        self._knob_x = self._knob_max_x if is_dark else self._knob_min_x
        self._draw()