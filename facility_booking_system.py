"""
facility_booking_system.py
University Facilities Booking App - Tkinter GUI
--------------------------------------------------
Run with:  python facility_booking_system.py

Top level of the Facility Booking System. This module owns the pieces that
sit above the five functional modules of the system chart: the shared page
helpers, the BaseTab every screen inherits from, the login window, and the
two application shells (admin + student) that wire the module screens
together.

The five functional modules live in their own files:
  receive_application.py        - member/application intake, ID + credentials
  approve_decline_application.py- approve / refuse / pending decisions
  booking_facilities.py         - booking screens, facilities, availability
  amend_cancel_booking.py       - amendments, cancellations, refunds
  generate_report.py            - dashboard stats + report export

Visual layer: theme.py (colours/ttk styles), widgets.py (image carousel,
row-hover highlight, confirmation prompts), assets.py (procedurally
generated facility photo-cards used by the carousel).

The module screens import BaseTab and the shared helpers from here, so the
tab classes are imported inside `_build_ui` rather than at module level -
that keeps the import cycle from closing while leaving behaviour unchanged.
"""


import tkinter as tk
from tkinter import ttk
from pathlib import Path

from database import (Database, UserManager, FacilityManager, BookingManager,
                     MaintenanceManager, UsageManager, AuthManager, StudentAuthManager)
import theme
import assets
from widgets import (attach_row_hover, confirm, NavItem, shadow_wrap, page_header,
                    ThemeToggle, ToastManager, ScrollableFrame)

APP_TITLE = "University Facilities Booking App"
BASE_DIR = Path(__file__).resolve().parent
LOGO_CANDIDATES = (
    BASE_DIR / "Logo Picture" / "logo.png",
    BASE_DIR / "Logo Picture" / "Logo.png.png",
)


# ==========================================================================
# small shared helpers
# ==========================================================================
def tag_for_status(status):
    return f"status_{status}"


def tag_for_condition(condition):
    return f"cond_{condition}"


def style_new_tree(tree):
    theme.style_treeview_tags(tree)
    attach_row_hover(tree)
    
def sort_treeview(tree, col, reverse=False):
    data = []

    for item in tree.get_children():
        value = tree.set(item, col)

        # Try sorting as numbers
        try:
            value = float(value)
        except ValueError:
            value = value.lower()

        data.append((value, item))

    data.sort(reverse=reverse)

    for index, (_, item) in enumerate(data):
        tree.move(item, "", index)

    # Reset all headings
    for c in tree["columns"]:
        tree.heading(
            c,
            text=c,
            command=lambda c=c: sort_treeview(tree, c, False)
        )

    arrow = " ▲" if reverse else " ▼"

    tree.heading(
        col,
        text=col + arrow,
        command=lambda: sort_treeview(tree, col, not reverse)
    )

def enable_sort(tree):
    for col in tree["columns"]:
        tree.heading(
            col,
            text=col,
            command=lambda c=col: sort_treeview(tree, c, False)
        )    

def load_logo_image(size):
    for path in LOGO_CANDIDATES:
        if path.exists():
            try:
                from PIL import Image, ImageTk
                image = Image.open(path).resize((size, size), Image.LANCZOS)
                return ImageTk.PhotoImage(image)
            except Exception:
                try:
                    return tk.PhotoImage(file=str(path))
                except Exception:
                    return None
    return None


def logo_widget(master, size, bg):
    photo = load_logo_image(size)
    if photo:
        label = tk.Label(master, image=photo, bg=bg, width=size, height=size)
        label.image = photo
        return label

    logo = tk.Canvas(master, width=size, height=size, highlightthickness=0, bg=bg)
    logo.create_rectangle(0, 0, size, size, fill=theme.PRIMARY, outline="")
    logo.create_text(size // 2, size // 2, text="UF", fill="white",
                     font=(theme.FONT_FAMILY, max(10, size // 3), "bold"))
    return logo


def facility_caption(f):
    return f"{f['name']}  ({f['type']}, {f['location'] or 'Unassigned'})"

# ==========================================================================
# Base class for every tab in the sidebar
# ==========================================================================
class BaseTab(ttk.Frame):
    """
    Common lifecycle shared by every tab: build the widgets once in
    `_build_ui()`, then load live data in `refresh()`. Subclasses only need
    to implement those two methods - the constructor boilerplate that used
    to be copy-pasted into every tab (padding, keeping a reference to the
    app, build-then-refresh) now lives here exactly once.

    If a subclass needs extra constructor arguments (e.g. `BookingTab`'s
    `category` / `type_options`), set them as attributes *before* calling
    `super().__init__(...)`, since `_build_ui()` runs during that call.
    """
    PADDING = 14

    def __init__(self, master, app):
        super().__init__(master, padding=self.PADDING)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        raise NotImplementedError("Subclasses must implement _build_ui().")

    def refresh(self):
        raise NotImplementedError("Subclasses must implement refresh().")

    # ---- small helpers reused by most tabs ----------------------------
    def _page_header(self, title, subtitle=None):
        return page_header(self, title, subtitle)

    def _setup_tree(self, tree):
        """Applies the shared styling/hover/click-to-sort behaviour to a Treeview."""
        style_new_tree(tree)
        enable_sort(tree)

    def toast(self, message, kind="success"):
        """Non-blocking notification in the corner of the window, instead of
        a modal messagebox, for routine confirmations (saved/added/updated)."""
        self.app.show_toast(message, kind=kind)


# ==========================================================================
# Login window - admin-only gate shown before the main application
# ==========================================================================
class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Sign In - {APP_TITLE}")
        self.geometry("1300x780")
        self.resizable(False, False)
        theme.apply_theme(self)
        self.configure(bg=theme.BG)

        self.authenticated = False
        self.username = None
        self.login_role = None          # "admin" or "student", once signed in
        self.student_user = None        # the users-table row for a student sign-in

        self.db = Database()
        self.auth_mgr = AuthManager(self.db)
        self.user_mgr = UserManager(self.db)
        self.student_auth = StudentAuthManager(self.db, self.user_mgr)

        self._mode = "admin"
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build_ui(self):
        center = tk.Frame(self, bg=theme.BG)
        center.pack(expand=True)

        card_shadow, card = shadow_wrap(center)
        card_shadow.pack(padx=10, pady=10)
        card.pack_propagate(False)
        card.configure(width=860, height=560)

        row = tk.Frame(card, bg=theme.SURFACE)
        row.pack(fill="both", expand=True)

        # ---- left: gradient brand panel (baked-in title/tagline image) ----
        from PIL import Image, ImageTk
        panel_size = (340, 560)
        panel_path = assets.get_brand_panel(panel_size, title="Facilities Hub",
                                             subtitle="Book smarter. Manage better.")
        self._brand_photo = ImageTk.PhotoImage(Image.open(panel_path))
        brand = tk.Label(row, image=self._brand_photo, bd=0)
        brand.pack(side="left", fill="y")

        # ---- right: sign-in form ----
        wrap = tk.Frame(row, bg=theme.SURFACE, width=520)
        wrap.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(wrap, bg=theme.SURFACE)
        inner.place(relx=0.5, rely=0.5, anchor="center")

        # ---- mode switch: Staff/Admin vs Student ----
        toggle_row = tk.Frame(inner, bg=theme.SURFACE)
        toggle_row.pack(anchor="w", pady=(0, 20))
        self.admin_mode_btn = ttk.Button(toggle_row, text="Staff / Admin", width=14,
                                          command=lambda: self._set_mode("admin"))
        self.admin_mode_btn.pack(side="left")
        self.student_mode_btn = ttk.Button(toggle_row, text="Student", width=14,
                                            command=lambda: self._set_mode("student"))
        self.student_mode_btn.pack(side="left", padx=(6, 0))

        self.form_frame = tk.Frame(inner, bg=theme.SURFACE, width=340)
        self.form_frame.pack(fill="both")

        self._build_admin_form()
        self._build_student_form()
        self._set_mode("admin")

    # ---- admin (staff) sign-in form ---------------------------------------
    def _build_admin_form(self):
        f = self.admin_form = tk.Frame(self.form_frame, bg=theme.SURFACE)

        tk.Label(f, text="Welcome back", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 18, "bold")).pack(anchor="w")
        tk.Label(f, text="Sign in with your administrator account to continue.",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, wraplength=320, justify="left",
                 font=(theme.FONT_FAMILY, 9)).pack(anchor="w", pady=(4, 26))

        tk.Label(f, text="Username", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w")
        self.username_entry = ttk.Entry(f, width=30)
        self.username_entry.pack(pady=(3, 14), fill="x")

        tk.Label(f, text="Password", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w")
        pw_row = tk.Frame(f, bg=theme.SURFACE)
        pw_row.pack(fill="x", pady=(3, 4))
        self.password_entry = ttk.Entry(pw_row, show="\u2022")
        self.password_entry.pack(side="left", fill="x", expand=True)
        self._show_pw = False
        self.toggle_btn = ttk.Button(pw_row, text="Show", width=6, style="Neutral.TButton",
                                      command=self._toggle_pw)
        self.toggle_btn.pack(side="left", padx=(6, 0))

        self.error_label = tk.Label(f, text="", bg=theme.SURFACE, fg=theme.DANGER,
                                     font=(theme.FONT_FAMILY, 9), wraplength=280, justify="left")
        self.error_label.pack(anchor="w", pady=(6, 12))

        ttk.Button(f, text="Sign In", style="Primary.TButton",
                   command=self._attempt_login).pack(fill="x")

        tk.Label(f, text=f"Default admin login: {AuthManager.DEFAULT_USERNAME} / "
                         f"{AuthManager.DEFAULT_PASSWORD}",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 8)).pack(pady=(18, 0))

        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus_set())
        self.password_entry.bind("<Return>", lambda e: self._attempt_login())

    def _toggle_pw(self):
        self._show_pw = not self._show_pw
        self.password_entry.configure(show="" if self._show_pw else "\u2022")
        self.toggle_btn.configure(text="Hide" if self._show_pw else "Show")

    def _attempt_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.error_label.configure(text="Please enter both username and password.")
            return
        if self.auth_mgr.verify_login(username, password):
            self.authenticated = True
            self.login_role = "admin"
            self.username = username
            self.db.close()
            self.destroy()
        else:
            self.error_label.configure(text="Invalid username or password. Please try again.")
            self.password_entry.delete(0, "end")
            self.password_entry.focus_set()

    # ---- student sign-in form ----------------------------------------------
    def _build_student_form(self):
        f = self.student_form = tk.Frame(self.form_frame, bg=theme.SURFACE)

        tk.Label(f, text="Student sign in", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 18, "bold")).pack(anchor="w")
        tk.Label(f, text="Sign in with your Student ID to book facilities, check "
                          "availability, and manage your profile.",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, wraplength=320, justify="left",
                 font=(theme.FONT_FAMILY, 9)).pack(anchor="w", pady=(4, 26))

        tk.Label(f, text="Student ID", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w")
        self.sid_var = tk.StringVar()
        self.sid_entry = ttk.Entry(f, width=30, textvariable=self.sid_var)
        self.sid_entry.pack(pady=(3, 14), fill="x")
        self.sid_var.trace_add("write", self._auto_upper_sid)

        tk.Label(f, text="Password", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w")
        spw_row = tk.Frame(f, bg=theme.SURFACE)
        spw_row.pack(fill="x", pady=(3, 4))
        self.spassword_entry = ttk.Entry(spw_row, show="\u2022")
        self.spassword_entry.pack(side="left", fill="x", expand=True)
        self._show_spw = False
        self.stoggle_btn = ttk.Button(spw_row, text="Show", width=6, style="Neutral.TButton",
                                       command=self._toggle_spw)
        self.stoggle_btn.pack(side="left", padx=(6, 0))

        self.student_error_label = tk.Label(f, text="", bg=theme.SURFACE, fg=theme.DANGER,
                                             font=(theme.FONT_FAMILY, 9), wraplength=280, justify="left")
        self.student_error_label.pack(anchor="w", pady=(6, 12))

        ttk.Button(f, text="Sign In", style="Primary.TButton",
                   command=self._attempt_student_login).pack(fill="x")

        tk.Label(f, text="First time signing in? Enter your Student ID and choose a "
                          "password (6+ characters) - it will become your account password.",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, wraplength=320, justify="left",
                 font=(theme.FONT_FAMILY, 8)).pack(pady=(18, 0), anchor="w")

        self.sid_entry.bind("<Return>", lambda e: self.spassword_entry.focus_set())
        self.spassword_entry.bind("<Return>", lambda e: self._attempt_student_login())

    def _auto_upper_sid(self, *_args):
        current = self.sid_var.get()
        upper = current.upper()
        if upper != current:
            cursor = self.sid_entry.index("insert")
            self.sid_var.set(upper)
            self.sid_entry.icursor(cursor)

    def _toggle_spw(self):
        self._show_spw = not self._show_spw
        self.spassword_entry.configure(show="" if self._show_spw else "\u2022")
        self.stoggle_btn.configure(text="Hide" if self._show_spw else "Show")

    def _attempt_student_login(self):
        student_id = self.sid_entry.get().strip().upper()
        password = self.spassword_entry.get()
        if not student_id or not password:
            self.student_error_label.configure(text="Please enter both Student ID and password.")
            return
        student = self.student_auth.find_student(student_id)
        if student is None:
            self.student_error_label.configure(
                text="No student account found with that Student ID.")
            return
        first_time = not self.user_mgr.has_password(student["id"])
        user = self.student_auth.verify_login(student_id, password)
        if user is None:
            if first_time:
                self.student_error_label.configure(
                    text="Please choose a password of at least 6 characters.")
            else:
                self.student_error_label.configure(
                    text="Incorrect password. Please try again.")
            self.spassword_entry.delete(0, "end")
            self.spassword_entry.focus_set()
            return
        self.authenticated = True
        self.login_role = "student"
        self.student_user = user
        self.db.close()
        self.destroy()

    # ---- mode switching ----------------------------------------------------
    def _set_mode(self, mode):
        self._mode = mode
        is_admin = mode == "admin"
        self.admin_mode_btn.configure(style="Primary.TButton" if is_admin else "Neutral.TButton")
        self.student_mode_btn.configure(style="Neutral.TButton" if is_admin else "Primary.TButton")
        if is_admin:
            self.student_form.pack_forget()
            self.admin_form.pack(fill="both")
            self.username_entry.focus_set()
        else:
            self.admin_form.pack_forget()
            self.student_form.pack(fill="both")
            self.sid_entry.focus_set()

    def _on_cancel(self):
        self.authenticated = False
        try:
            self.db.close()
        except Exception:
            pass
        self.destroy()


# ==========================================================================
# Student portal application - the window shown after a student signs in
# ==========================================================================
class StudentApp(tk.Tk):
    def __init__(self, current_student):
        super().__init__()
        self.title(f"{APP_TITLE} - Student Portal")
        self.geometry("1180x740")
        self.minsize(1000, 640)

        self.current_student = current_student
        self.student_id = current_student["id"]
        self.logout_requested = False
        self._current_tab_key = "book"

        theme.apply_theme(self)

        self.db = Database()
        self.user_mgr = UserManager(self.db)
        self.facility_mgr = FacilityManager(self.db)
        self.booking_mgr = BookingManager(self.db, self.facility_mgr)

        self._toasts = ToastManager(self)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._due_check_job = None
        self._check_due_bookings()

    def show_toast(self, message, kind="success"):
        self._toasts.show(message, kind=kind)

    def _check_due_bookings(self):
        """Runs every 30s off the real clock: any of this student's
        'Approved' bookings whose end time has passed get auto-marked
        'Completed', with a toast per booking so it isn't a silent change."""
        try:
            completed = self.booking_mgr.auto_complete_due_bookings(user_id=self.student_id)
        except Exception:
            completed = []
        for b in completed:
            self.show_toast(
                f"'{b['facility_name']}' booking on {b['booking_date']} "
                f"({b['start_time']}\u2013{b['end_time']}) is now Completed \u2014 time's up.",
                kind="info")
        if completed and hasattr(self, "book_tab"):
            self.book_tab.refresh()
        self._due_check_job = self.after(30000, self._check_due_bookings)

    def _cancel_due_check(self):
        if self._due_check_job:
            try:
                self.after_cancel(self._due_check_job)
            except Exception:
                pass
            self._due_check_job = None

    def _build_ui(self):
        for child in self.winfo_children():
            child.destroy()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()

        content_outer = tk.Frame(self, bg=theme.BG)
        content_outer.grid(row=0, column=1, sticky="nsew")
        content_outer.grid_rowconfigure(1, weight=1)
        content_outer.grid_columnconfigure(0, weight=1)

        self._build_topbar(content_outer)

        self.content = tk.Frame(content_outer, bg=theme.BG)
        self.content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(10, 20))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._content_scroll = ScrollableFrame(self.content, bg=theme.BG)
        self._content_scroll.grid(row=0, column=0, sticky="nsew")
        tabs_parent = self._content_scroll.body

        from booking_facilities import StudentBookingTab, StudentAvailabilityTab
        from receive_application import StudentProfileTab

        self.book_tab = StudentBookingTab(tabs_parent, self)
        self.availability_tab = StudentAvailabilityTab(tabs_parent, self)
        self.profile_tab = StudentProfileTab(tabs_parent, self)

        self._tabs = {
            "book": self.book_tab,
            "availability": self.availability_tab,
            "profile": self.profile_tab,
        }
        for frame in self._tabs.values():
            frame.grid(row=0, column=0, sticky="nsew")
        tabs_parent.grid_rowconfigure(0, weight=1)
        tabs_parent.grid_columnconfigure(0, weight=1)

        self.show_tab(self._current_tab_key)

    def _build_topbar(self, parent):
        topbar = tk.Frame(parent, bg=theme.BG)
        topbar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))

        right = tk.Frame(topbar, bg=theme.BG)
        right.pack(side="right")

        is_dark = theme.AppTheme.MODE == "dark"
        self._theme_label = tk.Label(
            right, text="Dark Mode" if is_dark else "Light Mode",
            bg=theme.BG, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9, "bold"))
        self._theme_label.pack(side="left", padx=(0, 8))

        self.theme_toggle = ThemeToggle(right, is_dark=is_dark, container_bg=theme.BG,
                                         command=self._on_theme_toggle)
        self.theme_toggle.pack(side="left")

        return topbar

    def _on_theme_toggle(self, is_dark):
        old_mode = theme.AppTheme.MODE
        new_mode = "dark" if is_dark else "light"
        theme.set_mode(new_mode, root=self)
        theme.live_recolor(self, old_mode, new_mode)
        self._theme_label.configure(text="Dark Mode" if is_dark else "Light Mode")

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=theme.SIDEBAR_BG, width=220)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg=theme.SIDEBAR_BG)
        brand.pack(fill="x", padx=18, pady=(22, 18))
        logo = logo_widget(brand, 38, theme.SIDEBAR_BG)
        logo.pack(side="left")
        text_box = tk.Frame(brand, bg=theme.SIDEBAR_BG)
        text_box.pack(side="left", padx=(10, 0))
        tk.Label(text_box, text="Facilities Hub", bg=theme.SIDEBAR_BG, fg="white",
                 font=(theme.FONT_FAMILY, 12, "bold")).pack(anchor="w")
        tk.Label(text_box, text="Student Portal", bg=theme.SIDEBAR_BG, fg=theme.SIDEBAR_TEXT_MUTED,
                 font=(theme.FONT_FAMILY, 8)).pack(anchor="w")

        tk.Frame(sidebar, bg=theme.SIDEBAR_BG_HOVER, height=1).pack(fill="x", padx=18, pady=(0, 10))

        nav_defs = [
            ("book", "\U0001F4C5", "Book a Facility"),
            ("availability", "\U0001F50D", "Check Availability"),
            ("profile", "\U0001F464", "My Profile"),
        ]
        self._nav_items = {}
        for key, icon, label in nav_defs:
            item = NavItem(sidebar, icon, label, command=lambda k=key: self.show_tab(k))
            item.pack(fill="x", padx=10, pady=2)
            self._nav_items[key] = item

        footer = tk.Frame(sidebar, bg=theme.SIDEBAR_BG)
        footer.pack(side="bottom", fill="x", padx=18, pady=16)
        tk.Label(footer, text=f"Signed in as {self.current_student['name']}", bg=theme.SIDEBAR_BG,
                 fg=theme.SIDEBAR_TEXT_MUTED, font=(theme.FONT_FAMILY, 8)).pack(anchor="w")
        logout_lbl = tk.Label(footer, text="\u23FB  Log Out", bg=theme.SIDEBAR_BG,
                               fg=theme.SIDEBAR_ACCENT, font=(theme.FONT_FAMILY, 9, "bold"),
                               cursor="hand2")
        logout_lbl.pack(anchor="w", pady=(8, 0))
        logout_lbl.bind("<Button-1>", lambda e: self._request_logout())
        logout_lbl.bind("<Enter>", lambda e: logout_lbl.configure(fg="white"))
        logout_lbl.bind("<Leave>", lambda e: logout_lbl.configure(fg=theme.SIDEBAR_ACCENT))

    def show_tab(self, key):
        self._current_tab_key = key
        for k, item in self._nav_items.items():
            item.set_active(k == key)
        frame = self._tabs[key]
        frame.tkraise()
        if hasattr(frame, "refresh"):
            frame.refresh()

    def _request_logout(self):
        if confirm("Log Out", "Are you sure you want to log out?"):
            self._cancel_due_check()
            self.logout_requested = True
            self.db.close()
            self.destroy()

    def _on_close(self):
        if confirm("Exit Application", "Are you sure you want to exit?"):
            self._cancel_due_check()
            self.db.close()
            self.destroy()


# ==========================================================================
# Main application
# ==========================================================================
class FacilityBookingApp(tk.Tk):
    def __init__(self, current_admin="Admin"):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1260x780")
        self.minsize(1100, 680)

        self.current_admin = current_admin
        self.logout_requested = False
        self._current_tab_key = "dashboard"

        theme.apply_theme(self)

        self.db = Database()
        self.user_mgr = UserManager(self.db)
        self.facility_mgr = FacilityManager(self.db)
        self.booking_mgr = BookingManager(self.db, self.facility_mgr)
        self.maintenance_mgr = MaintenanceManager(self.db, self.facility_mgr)
        self.usage_mgr = UsageManager(self.db)
        self.auth_mgr = AuthManager(self.db)

        self._toasts = ToastManager(self)
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._due_check_job = None
        self._check_due_bookings()

    def show_toast(self, message, kind="success"):
        self._toasts.show(message, kind=kind)

    def _check_due_bookings(self):
        """Runs every 30s off the real clock: any 'Approved' booking whose
        end time has passed - across every student and facility - gets
        auto-marked 'Completed', with a toast per booking so admin sees it
        happen instead of the status silently changing underneath them."""
        try:
            completed = self.booking_mgr.auto_complete_due_bookings()
        except Exception:
            completed = []
        for b in completed:
            self.show_toast(
                f"'{b['facility_name']}' booking for {b['user_name']} on {b['booking_date']} "
                f"({b['start_time']}\u2013{b['end_time']}) is now Completed \u2014 time's up.",
                kind="info")
        if completed:
            self.refresh_all_booking_tabs()
            self.refresh_dashboard()
        self._due_check_job = self.after(30000, self._check_due_bookings)

    def _cancel_due_check(self):
        if self._due_check_job:
            try:
                self.after_cancel(self._due_check_job)
            except Exception:
                pass
            self._due_check_job = None

    # ---- (re)builds the whole window body -------------------------------
    def _build_ui(self):
        """Builds the sidebar + topbar + tabs. Called once at startup only -
        a light/dark mode switch now recolours the existing widgets in place
        (see `theme.live_recolor`) instead of rebuilding anything."""
        for child in self.winfo_children():
            child.destroy()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._build_sidebar()

        content_outer = tk.Frame(self, bg=theme.BG)
        content_outer.grid(row=0, column=1, sticky="nsew")
        content_outer.grid_rowconfigure(1, weight=1)
        content_outer.grid_columnconfigure(0, weight=1)

        self._build_topbar(content_outer)

        self.content = tk.Frame(content_outer, bg=theme.BG)
        self.content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(10, 20))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self._content_scroll = ScrollableFrame(self.content, bg=theme.BG)
        self._content_scroll.grid(row=0, column=0, sticky="nsew")
        tabs_parent = self._content_scroll.body

        from generate_report import DashboardTab, ReportsTab
        from booking_facilities import BookingTab, FacilityTab, MaintenanceTab
        from receive_application import UserTab, AdminProfileTab

        self.dashboard_tab = DashboardTab(tabs_parent, self)
        self.room_tab = BookingTab(tabs_parent, self, "Room", ["Lecture Hall", "Classroom", "Lab"])
        self.sports_tab = BookingTab(tabs_parent, self, "Sports", ["Gym", "Court", "Pool", "Field"])
        self.equipment_tab = BookingTab(tabs_parent, self, "Equipment",
                                         ["Projector", "Laptop", "Lab Instrument"])
        self.facility_tab = FacilityTab(tabs_parent, self)
        self.maintenance_tab = MaintenanceTab(tabs_parent, self)
        self.reports_tab = ReportsTab(tabs_parent, self)
        self.users_tab = UserTab(tabs_parent, self)
        self.admin_profile_tab = AdminProfileTab(tabs_parent, self)

        self._tabs = {
            "dashboard": self.dashboard_tab,
            "room": self.room_tab,
            "sports": self.sports_tab,
            "equipment": self.equipment_tab,
            "facility": self.facility_tab,
            "maintenance": self.maintenance_tab,
            "users": self.users_tab,
            "reports": self.reports_tab,
            "admin_profile": self.admin_profile_tab,
        }
        for frame in self._tabs.values():
            frame.grid(row=0, column=0, sticky="nsew")
        tabs_parent.grid_rowconfigure(0, weight=1)
        tabs_parent.grid_columnconfigure(0, weight=1)

        self.show_tab(self._current_tab_key)

    def _build_topbar(self, parent):
        """Thin bar above the page content holding the light/dark switch,
        top-right."""
        topbar = tk.Frame(parent, bg=theme.BG)
        topbar.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 0))

        right = tk.Frame(topbar, bg=theme.BG)
        right.pack(side="right")

        is_dark = theme.AppTheme.MODE == "dark"
        self._theme_label = tk.Label(
            right, text="Dark Mode" if is_dark else "Light Mode",
            bg=theme.BG, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9, "bold"))
        self._theme_label.pack(side="left", padx=(0, 8))

        self.theme_toggle = ThemeToggle(right, is_dark=is_dark, container_bg=theme.BG,
                                         command=self._on_theme_toggle)
        self.theme_toggle.pack(side="left")

        return topbar

    def _on_theme_toggle(self, is_dark):
        old_mode = theme.AppTheme.MODE
        new_mode = "dark" if is_dark else "light"
        theme.set_mode(new_mode, root=self)
        theme.live_recolor(self, old_mode, new_mode)
        self._theme_label.configure(text="Dark Mode" if is_dark else "Light Mode")

    def _build_sidebar(self):
        sidebar = tk.Frame(self, bg=theme.SIDEBAR_BG, width=220)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg=theme.SIDEBAR_BG)
        brand.pack(fill="x", padx=18, pady=(22, 18))
        logo = logo_widget(brand, 38, theme.SIDEBAR_BG)
        logo.pack(side="left")
        text_box = tk.Frame(brand, bg=theme.SIDEBAR_BG)
        text_box.pack(side="left", padx=(10, 0))
        tk.Label(text_box, text="Facilities Hub", bg=theme.SIDEBAR_BG, fg="white",
                 font=(theme.FONT_FAMILY, 12, "bold")).pack(anchor="w")
        tk.Label(text_box, text="Booking System", bg=theme.SIDEBAR_BG, fg=theme.SIDEBAR_TEXT_MUTED,
                 font=(theme.FONT_FAMILY, 8)).pack(anchor="w")

        tk.Frame(sidebar, bg=theme.SIDEBAR_BG_HOVER, height=1).pack(fill="x", padx=18, pady=(0, 10))

        nav_defs = [
            ("dashboard", "\U0001F3E0", "Dashboard"),
            ("room", "\U0001F3EB", "Room Reservations"),
            ("sports", "\U0001F3C0", "Sports & Recreation"),
            ("equipment", "\U0001F4FD", "Equipment Booking"),
            ("facility", "\U0001F5C2", "Facility & Resources"),
            ("maintenance", "\U0001F6E0", "Usage & Maintenance"),
            ("users", "\U0001F464", "Manage Users"),
            ("reports", "\U0001F4CA", "Reports"),
            ("admin_profile", "\U0001F9D1", "My Profile"),

        ]
        self._nav_items = {}
        for key, icon, label in nav_defs:
            item = NavItem(sidebar, icon, label, command=lambda k=key: self.show_tab(k))
            item.pack(fill="x", padx=10, pady=2)
            self._nav_items[key] = item

        footer = tk.Frame(sidebar, bg=theme.SIDEBAR_BG)
        footer.pack(side="bottom", fill="x", padx=18, pady=16)
        tk.Label(footer, text=f"Signed in as {self.current_admin}", bg=theme.SIDEBAR_BG,
                 fg=theme.SIDEBAR_TEXT_MUTED, font=(theme.FONT_FAMILY, 8)).pack(anchor="w")
        logout_lbl = tk.Label(footer, text="\u23FB  Log Out", bg=theme.SIDEBAR_BG,
                               fg=theme.SIDEBAR_ACCENT, font=(theme.FONT_FAMILY, 9, "bold"),
                               cursor="hand2")
        logout_lbl.pack(anchor="w", pady=(8, 0))
        logout_lbl.bind("<Button-1>", lambda e: self._request_logout())
        logout_lbl.bind("<Enter>", lambda e: logout_lbl.configure(fg="white"))
        logout_lbl.bind("<Leave>", lambda e: logout_lbl.configure(fg=theme.SIDEBAR_ACCENT))

    def show_tab(self, key):
        self._current_tab_key = key
        for k, item in self._nav_items.items():
            item.set_active(k == key)
        frame = self._tabs[key]
        frame.tkraise()
        if hasattr(frame, "refresh"):
            frame.refresh()

    def refresh_all_booking_tabs(self):
        for t in (self.room_tab, self.sports_tab, self.equipment_tab):
            t.refresh()

    def refresh_dashboard(self):
        self.dashboard_tab.refresh()

    def _request_logout(self):
        if confirm("Log Out", "Are you sure you want to log out?"):
            self._cancel_due_check()
            self.logout_requested = True
            self.db.close()
            self.destroy()

    def _on_close(self):
        if confirm("Exit Application", "Are you sure you want to exit?"):
            self._cancel_due_check()
            self.db.close()
            self.destroy()


if __name__ == "__main__":
    while True:
        login = LoginWindow()
        login.mainloop()
        if not login.authenticated:
            break
        if login.login_role == "student":
            app = StudentApp(current_student=login.student_user)
        else:
            app = FacilityBookingApp(current_admin=login.username)
        app.mainloop()
        if not app.logout_requested:
            break
