"""
receive_application.py
Facility Booking System - module 1: Receive Application
------------------------------------------------------
Everything to do with taking in and holding a member's application record:

  Verify Member Details    - UserTab form validation + the scanned/typed
                             student ID checks
  Process Application      - add / update / delete the member record,
                             photo upload, password credentials
  Generate Application ID  - the student ID + barcode number issued to the
                             member and rendered onto their card

The two profile screens live here as well, since they are the same member
record being viewed and edited by its owner rather than by an admin.
"""


import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

import theme
import assets
import barcode_gen
from id_scanner import CameraScanDialog
from widgets import ImageCarousel, restripe, confirm, shadow_wrap, DateEntry, EmptyState

from facility_booking_system import BaseTab

# ==========================================================================
# Small modal: admin sets/resets a user's password directly. Passwords are
# always hashed at rest (see UserManager.set_password) so there's no way to
# *view* the current one - this dialog only ever writes a brand-new one.
# ==========================================================================
class SetPasswordDialog(tk.Toplevel):
    def __init__(self, master, target_name, on_submit):
        super().__init__(master)
        self.title(f"Set Password - {target_name}")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.on_submit = on_submit

        pad = ttk.Frame(self, padding=18)
        pad.pack(fill="both", expand=True)
        ttk.Label(pad, text=f"New password for {target_name}",
                  style="SubHeading.TLabel").pack(anchor="w")
        ttk.Label(pad, text="At least 6 characters. This immediately replaces their "
                            "current password - it can't be viewed afterwards, only reset again.",
                  style="Muted.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=(4, 14))

        ttk.Label(pad, text="New Password:").pack(anchor="w")
        self.new_entry = ttk.Entry(pad, show="\u2022", width=30)
        self.new_entry.pack(anchor="w", pady=(2, 10))
        self.new_entry.bind("<KeyRelease>", lambda e: self._live_check())

        ttk.Label(pad, text="Confirm Password:").pack(anchor="w")
        self.confirm_entry = ttk.Entry(pad, show="\u2022", width=30)
        self.confirm_entry.pack(anchor="w", pady=(2, 4))
        self.confirm_entry.bind("<KeyRelease>", lambda e: self._live_check())

        self.status_lbl = ttk.Label(pad, text="", style="Muted.TLabel", wraplength=300, justify="left")
        self.status_lbl.pack(anchor="w", pady=(4, 12))

        btns = ttk.Frame(pad)
        btns.pack(fill="x")
        ttk.Button(btns, text="Save Password", style="Primary.TButton",
                   command=self._submit).pack(side="right")
        ttk.Button(btns, text="Cancel", style="Neutral.TButton",
                   command=self.destroy).pack(side="right", padx=(0, 6))

        self.new_entry.focus_set()
        self.bind("<Return>", lambda e: self._submit())
        self.bind("<Escape>", lambda e: self.destroy())

    def _live_check(self):
        """Updates the status line as the admin types, before Save is even
        clicked - so a mismatch or too-short password is obvious right away
        instead of only surfacing after submitting."""
        new = self.new_entry.get()
        conf = self.confirm_entry.get()
        if not new and not conf:
            self.status_lbl.configure(text="", foreground=theme.MUTED_TEXT)
        elif len(new) < 6:
            self.status_lbl.configure(text="Password must be at least 6 characters.",
                                       foreground=theme.MUTED_TEXT)
        elif not conf:
            self.status_lbl.configure(text="Now confirm the password below.",
                                       foreground=theme.MUTED_TEXT)
        elif new != conf:
            self.status_lbl.configure(text="\u2717 Passwords do not match.", foreground=theme.DANGER)
        else:
            self.status_lbl.configure(text="\u2713 Passwords match.", foreground=theme.SUCCESS)

    def _submit(self):
        new = self.new_entry.get()
        conf = self.confirm_entry.get()
        if new != conf:
            self.status_lbl.configure(text="\u2717 Passwords do not match.", foreground=theme.DANGER)
            return
        try:
            self.on_submit(new)
        except ValueError as exc:
            self.status_lbl.configure(text=str(exc), foreground=theme.DANGER)
            return
        self.destroy()


# ==========================================================================
# Manage Users tab - user directory, ID card capture, photos & passwords
# ==========================================================================
class UserTab(BaseTab):
    AVATAR_SIZE = 100

    def __init__(self, master, app):
        self._selected_id = None
        self._directory_slide_ids = []
        self._directory_id_to_slide = {}
        super().__init__(master, app)

    def _build_ui(self):
        self._page_header("Manage Users",
                           "Add and update user records, scan a student ID card with your webcam, "
                           "manage profile photos, and set or reset passwords.")

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)

        body = ttk.Frame(content)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        preview_outer, preview_card = shadow_wrap(body)
        preview_outer.pack(side="right", fill="y", padx=(14, 0))
        right = tk.Frame(preview_card, bg=theme.SURFACE, width=250)
        right.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(right, text="SELECTED USER", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w")

        self.avatar_canvas = tk.Canvas(right, width=self.AVATAR_SIZE, height=self.AVATAR_SIZE,
                                        highlightthickness=0, bg=theme.NEUTRAL)
        self.avatar_canvas.pack(pady=(8, 6))
        self._avatar_photo = None

        self.user_name_lbl = tk.Label(right, text="No user selected", bg=theme.SURFACE, fg=theme.TEXT,
                                       font=(theme.FONT_FAMILY, 12, "bold"), wraplength=210, justify="center")
        self.user_name_lbl.pack()
        self.user_role_lbl = tk.Label(right, text="", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                       font=(theme.FONT_FAMILY, 9))
        self.user_role_lbl.pack(pady=(0, 10))

        ttk.Button(right, text="Upload Photo", style="Neutral.TButton",
                   command=self.upload_photo).pack(fill="x", pady=(0, 8))

        self.pw_status_lbl = tk.Label(right, text="", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                       font=(theme.FONT_FAMILY, 9, "bold"), wraplength=210, justify="left")
        self.pw_status_lbl.pack(anchor="w", pady=(2, 6))
        ttk.Button(right, text="Set / Reset Password", style="Primary.TButton",
                   command=self.open_password_dialog).pack(fill="x")

        tk.Frame(right, bg=theme.BORDER, height=1).pack(fill="x", pady=12)

        tk.Label(right, text="BARCODE PREVIEW", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 8))
        self.barcode_canvas = tk.Canvas(right, width=250, height=100, highlightthickness=0,
                                         bg=theme.SURFACE)
        self.barcode_canvas.pack()
        self._barcode_photo = None
        self._draw_barcode_placeholder("Select a user\nor scan a card")

        form = ttk.LabelFrame(left, text="Add / Update User Record",
                               style="Card.TLabelframe", padding=12)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Name:").grid(row=0, column=0, padx=4, pady=5, sticky="w")
        self.name_entry = ttk.Entry(form, width=22)
        self.name_entry.grid(row=0, column=1, padx=4, pady=5)

        ttk.Label(form, text="Role:").grid(row=0, column=2, padx=4, pady=5, sticky="w")
        self.role_cb = ttk.Combobox(form, state="readonly", width=12,
                                     values=["Student", "Faculty", "Staff", "Admin"])
        self.role_cb.current(0)
        self.role_cb.grid(row=0, column=3, padx=4, pady=5)

        ttk.Label(form, text="Email:").grid(row=0, column=4, padx=4, pady=5, sticky="w")
        self.email_entry = ttk.Entry(form, width=22)
        self.email_entry.grid(row=0, column=5, padx=4, pady=5)

        ttk.Label(form, text="Student ID:").grid(row=1, column=0, padx=4, pady=5, sticky="w")
        self.sid_var = tk.StringVar()
        self.sid_entry = ttk.Entry(form, width=22, textvariable=self.sid_var)
        self.sid_entry.grid(row=1, column=1, padx=4, pady=5)
        self.sid_var.trace_add("write", self._auto_upper_sid)
        ttk.Label(form, text="format: 23WMR12345", style="Muted.TLabel").grid(
            row=1, column=1, padx=(4, 0), pady=(24, 0), sticky="w")

        ttk.Label(form, text="Expiry Date:").grid(row=1, column=2, padx=4, pady=5, sticky="w")
        self.expiry_entry = DateEntry(form, order="dmy", width=11)
        self.expiry_entry.grid(row=1, column=3, padx=4, pady=5, sticky="w")
        ttk.Label(form, text="format: DD-MM-YYYY", style="Muted.TLabel").grid(
            row=1, column=3, padx=(4, 0), pady=(24, 0), sticky="w")

        ttk.Label(form, text="Barcode No.:").grid(row=1, column=4, padx=4, pady=5, sticky="w")
        self.barcode_entry = ttk.Entry(form, width=18)
        self.barcode_entry.grid(row=1, column=5, padx=4, pady=5)
        self.barcode_entry.bind("<KeyRelease>", lambda e: self._preview_typed_barcode())

        btns = ttk.Frame(form)
        btns.grid(row=2, column=0, columnspan=6, pady=(10, 2))
        ttk.Button(btns, text="\U0001F4F7 Scan ID Card (Webcam)", style="Success.TButton",
                   command=self.open_scanner).pack(side="left", padx=4)
        ttk.Button(btns, text="Add New User", style="Primary.TButton",
                   command=self.add_user).pack(side="left", padx=4)
        ttk.Button(btns, text="Update Selected", style="Neutral.TButton",
                   command=self.update_user).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete Selected", style="Danger.TButton",
                   command=self.delete_user).pack(side="left", padx=4)
        ttk.Button(btns, text="Clear Form", style="Ghost.TButton",
                   command=self._clear_form).pack(side="left", padx=4)

        table_header = ttk.Frame(left)
        table_header.pack(fill="x", pady=(0, 4))
        self.result_lbl = ttk.Label(table_header, style="Muted.TLabel", text="")
        self.result_lbl.pack(side="right")

        table_wrap = ttk.Frame(left, style="Surface.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("id", "name", "role", "email", "student_id", "expiry_date",
                   "barcode_number", "password_status")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=12)
        headers = ["ID", "Name", "Role", "Email", "Student ID", "Expiry", "Barcode No.", "Password"]
        widths = [36, 140, 75, 160, 95, 85, 100, 90]
        for c, h, w in zip(columns, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)
        self.tree.tag_configure("pw_set", foreground=theme.SUCCESS)
        self.tree.tag_configure("pw_unset", foreground=theme.MUTED_TEXT)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._empty_state = EmptyState(
            table_wrap, icon="\U0001F465", title="No users yet",
            subtitle="Add your first user with the form above, or scan a student ID card.")

        showcase_outer, showcase_card = shadow_wrap(content)
        showcase_outer.pack(fill="x", pady=(14, 0))
        showcase_inner = tk.Frame(showcase_card, bg=theme.SURFACE)
        showcase_inner.pack(fill="both", expand=True, padx=14, pady=12)
        tk.Label(showcase_inner, text="USER DIRECTORY SHOWCASE", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.directory_carousel = ImageCarousel(showcase_inner, width=680, height=150,
                                                 autoplay_ms=5000, on_select=self._select_from_carousel)
        self.directory_carousel.pack()

    # ---- avatar preview ----------------------------------------------------
    def _render_avatar(self, user=None):
        self.avatar_canvas.delete("all")
        size = self.AVATAR_SIZE
        if user is None:
            self.avatar_canvas.create_rectangle(0, 0, size, size, fill=theme.NEUTRAL, outline="")
            self.avatar_canvas.create_text(size / 2, size / 2, text="?",
                                            font=(theme.FONT_FAMILY, 26, "bold"), fill=theme.MUTED_TEXT)
            return
        custom = user["profile_picture"] if "profile_picture" in user.keys() else None
        path = assets.get_avatar("user", user["id"], user["name"], role=user["role"], custom_path=custom)
        from PIL import Image, ImageTk
        img = Image.open(path).resize((size, size), Image.LANCZOS)
        self._avatar_photo = ImageTk.PhotoImage(img)
        self.avatar_canvas.create_image(0, 0, anchor="nw", image=self._avatar_photo)

    def _update_password_status(self, user):
        has_pw = self.app.user_mgr.has_password(user["id"])
        if has_pw:
            self.pw_status_lbl.configure(text="\u2713 Password set", foreground=theme.SUCCESS)
        else:
            self.pw_status_lbl.configure(
                text="No password yet - claimed on the user's first student-portal sign-in.",
                foreground=theme.MUTED_TEXT)

    # ---- barcode preview -------------------------------------------------
    def _draw_barcode_placeholder(self, message):
        self.barcode_canvas.delete("all")
        self.barcode_canvas.create_rectangle(0, 0, 250, 100, fill=theme.NEUTRAL, outline="")
        self.barcode_canvas.create_text(125, 50, text=message, fill=theme.MUTED_TEXT,
                                         font=(theme.FONT_FAMILY, 9), justify="center")

    def _show_barcode_for(self, number):
        path = barcode_gen.get_barcode_image(number) if number else None
        if not path:
            self._draw_barcode_placeholder("No barcode number\non file for this user")
            return
        from PIL import Image, ImageTk
        img = Image.open(path)
        img.thumbnail((240, 90))
        self._barcode_photo = ImageTk.PhotoImage(img)
        self.barcode_canvas.delete("all")
        self.barcode_canvas.create_image(125, 50, image=self._barcode_photo)

    def _preview_typed_barcode(self):
        self._show_barcode_for(self.barcode_entry.get().strip())

    def _auto_upper_sid(self, *_args):
        current = self.sid_var.get()
        upper = current.upper()
        if upper != current:
            cursor = self.sid_entry.index("insert")
            self.sid_var.set(upper)
            self.sid_entry.icursor(cursor)

    # ---- directory showcase carousel ---------------------------------------
    def _select_from_carousel(self, index):
        if index < len(self._directory_slide_ids):
            uid = self._directory_slide_ids[index]
            if self.tree.exists(uid):
                self.tree.selection_set(uid)
                self.tree.see(uid)

    # ---- selection / form helpers -----------------------------------------
    def _on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        u = self.app.user_mgr.get_user(int(sel[0]))
        if u is None:
            return
        self._selected_id = u["id"]
        self.name_entry.delete(0, "end"); self.name_entry.insert(0, u["name"])
        self.role_cb.set(u["role"])
        self.email_entry.delete(0, "end"); self.email_entry.insert(0, u["email"] or "")
        self.sid_entry.delete(0, "end"); self.sid_entry.insert(0, u["student_id"] or "")
        self.expiry_entry.delete(0, "end"); self.expiry_entry.insert(0, u["expiry_date"] or "")
        self.barcode_entry.delete(0, "end"); self.barcode_entry.insert(0, u["barcode_number"] or "")
        self._show_barcode_for(u["barcode_number"])
        self.user_name_lbl.configure(text=u["name"])
        self.user_role_lbl.configure(text=u["role"])
        self._render_avatar(u)
        self._update_password_status(u)
        if u["id"] in self._directory_id_to_slide:
            self.directory_carousel.go_to(self._directory_id_to_slide[u["id"]])

    def _clear_form(self):
        self._selected_id = None
        self.tree.selection_remove(self.tree.selection())
        for entry in (self.name_entry, self.email_entry, self.sid_entry,
                      self.expiry_entry, self.barcode_entry):
            entry.delete(0, "end")
        self.role_cb.current(0)
        self._draw_barcode_placeholder("Select a user\nor scan a card")
        self.user_name_lbl.configure(text="No user selected")
        self.user_role_lbl.configure(text="")
        self.pw_status_lbl.configure(text="")
        self._render_avatar(None)

    def _collect_form(self):
        return dict(
            name=self.name_entry.get().strip(),
            role=self.role_cb.get(),
            email=self.email_entry.get().strip(),
            student_id=self.sid_entry.get().strip().upper(),
            expiry_date=self.expiry_entry.get().strip(),
            barcode_number=self.barcode_entry.get().strip(),
        )

    def _missing_user_fields(self, data):
        labels = {
            "name": "Name",
            "role": "Role",
            "email": "Email",
            "student_id": "Student ID",
            "expiry_date": "Expiry Date",
            "barcode_number": "Barcode No.",
        }
        return [label for key, label in labels.items() if not data.get(key)]

    # ---- webcam scan -------------------------------------------------------
    def open_scanner(self):
        CameraScanDialog(self, on_result=self._apply_scan_result)

    def _apply_scan_result(self, fields):
        """Called immediately after each capture in the scan dialog - fills
        in whatever was detected. Student ID cards don't print an email or
        role, so those two are auto-filled from the student ID instead of
        being left blank (still editable, same as every other field)."""
        if fields.get("name"):
            self.name_entry.delete(0, "end"); self.name_entry.insert(0, fields["name"])
        if fields.get("student_id"):
            self.sid_entry.delete(0, "end"); self.sid_entry.insert(0, fields["student_id"])
            self.role_cb.set(self.app.user_mgr.DEFAULT_SCAN_ROLE)
            if not self.email_entry.get().strip():
                suggested = self.app.user_mgr.suggest_email(fields["student_id"])
                if suggested:
                    self.email_entry.delete(0, "end"); self.email_entry.insert(0, suggested)
        if fields.get("expiry_date"):
            self.expiry_entry.delete(0, "end"); self.expiry_entry.insert(0, fields["expiry_date"])
        if fields.get("barcode_number"):
            self.barcode_entry.delete(0, "end"); self.barcode_entry.insert(0, fields["barcode_number"])
            self._show_barcode_for(fields["barcode_number"])

    # ---- CRUD --------------------------------------------------------------
    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        users = self.app.user_mgr.list_users()
        for u in users:
            has_pw = self.app.user_mgr.has_password(u["id"])
            self.tree.insert("", "end", iid=u["id"], values=(
                u["id"], u["name"], u["role"], u["email"] or "",
                u["student_id"] or "", u["expiry_date"] or "", u["barcode_number"] or "",
                "Set" if has_pw else "Not set"
            ), tags=("pw_set" if has_pw else "pw_unset",))
        restripe(self.tree)
        count = len(users)
        self.result_lbl.configure(text=f"{count} user{'s' if count != 1 else ''}")
        if count:
            self._empty_state.hide()
        else:
            self._empty_state.show()

        paths = [assets.get_person_card(
                    "user", u["id"], u["name"], role=u["role"],
                    subtitle=f"{u['role']}  •  {u['student_id'] or u['email'] or ''}",
                    status="Password set" if self.app.user_mgr.has_password(u["id"]) else "No password set",
                    custom_path=u["profile_picture"] if "profile_picture" in u.keys() else None)
                 for u in users]
        captions = [f"{u['name']}  ({u['role']})" for u in users]
        self._directory_slide_ids = [u["id"] for u in users]
        self._directory_id_to_slide = {uid: i for i, uid in enumerate(self._directory_slide_ids)}
        self.directory_carousel.set_slides(paths, captions)

        if self._selected_id is not None:
            u = self.app.user_mgr.get_user(self._selected_id)
            if u:
                self._update_password_status(u)

    def add_user(self):
        data = self._collect_form()
        missing = self._missing_user_fields(data)
        if missing:
            messagebox.showwarning("Missing info", "Please fill in: " + ", ".join(missing) + ".")
            return
        if not self.app.user_mgr.validate_email(data["email"]):
            messagebox.showwarning("Invalid email", "Please enter a valid email address.")
            return
        if not confirm("Confirm Add User", f"Add new user '{data['name']}' ({data['role']})?"):
            return
        try:
            self.app.user_mgr.add_user(**data)
        except ValueError as exc:
            messagebox.showerror("Invalid data", str(exc))
            return
        self.toast(f"User '{data['name']}' added.")
        self._clear_form()
        self.refresh()

    def update_user(self):
        if self._selected_id is None:
            messagebox.showwarning("No selection", "Select a user first.")
            return
        data = self._collect_form()
        missing = self._missing_user_fields(data)
        if missing:
            messagebox.showwarning("Missing info", "Please fill in: " + ", ".join(missing) + ".")
            return
        if not self.app.user_mgr.validate_email(data["email"]):
            messagebox.showwarning("Invalid email", "Please enter a valid email address.")
            return
        if not confirm("Confirm Update", f"Update record for '{data['name']}'?"):
            return
        try:
            self.app.user_mgr.update_user(self._selected_id, **data)
        except ValueError as exc:
            messagebox.showerror("Invalid data", str(exc))
            return
        self.toast("User record updated.")
        self.refresh()

    def delete_user(self):
        if self._selected_id is None:
            messagebox.showwarning("No selection", "Select a user first.")
            return
        u = self.app.user_mgr.get_user(self._selected_id)
        if confirm("Delete User", f"Delete '{u['name']}'? This cannot be undone.", danger=True):
            self.app.user_mgr.delete_user(self._selected_id)
            self._clear_form()
            self.refresh()

    # ---- photo & password management ---------------------------------------
    def upload_photo(self):
        if self._selected_id is None:
            messagebox.showwarning("No selection", "Select a user first.")
            return
        u = self.app.user_mgr.get_user(self._selected_id)
        path = filedialog.askopenfilename(
            title=f"Choose a profile photo for {u['name']}",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            saved_path = assets.save_profile_photo("user", u["id"], path)
            self.app.user_mgr.update_profile_picture(u["id"], saved_path)
        except Exception as exc:
            messagebox.showerror("Upload failed", str(exc))
            return
        self.toast(f"Profile photo updated for '{u['name']}'.")
        self.refresh()
        self.tree.selection_set(u["id"])
        self.tree.see(u["id"])

    def open_password_dialog(self):
        if self._selected_id is None:
            messagebox.showwarning("No selection", "Select a user first.")
            return
        u = self.app.user_mgr.get_user(self._selected_id)
        SetPasswordDialog(self, u["name"], on_submit=lambda pw: self._do_set_password(u["id"], u["name"], pw))

    def _do_set_password(self, user_id, name, new_password):
        self.app.user_mgr.set_password(user_id, new_password)  # raises ValueError if too short
        self.toast(f"Password for '{name}' has been set.")
        self.refresh()
        self.tree.selection_set(user_id)
        self.tree.see(user_id)


class StudentProfileTab(BaseTab):
    """
    Self-service profile: a student can update their own name/email,
    upload a profile picture, and reset their own password. Institutional
    card data (Student ID, card expiry, barcode number) stays read-only
    here - it can only be changed by facilities staff in Manage Users.
    """
    PIC_SIZE = 140

    def _build_ui(self):
        self._page_header("My Profile", "View your details, update your photo, and manage your password.")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left_outer, left_card = shadow_wrap(body)
        left_outer.pack(side="left", fill="y", padx=(0, 16))
        left = tk.Frame(left_card, bg=theme.SURFACE, width=220)
        left.pack(fill="both", expand=True, padx=18, pady=18)

        self.pic_canvas = tk.Canvas(left, width=self.PIC_SIZE, height=self.PIC_SIZE,
                                     highlightthickness=0, bg=theme.NEUTRAL)
        self.pic_canvas.pack()
        ttk.Button(left, text="Change Photo", style="Neutral.TButton",
                   command=self.change_photo).pack(pady=(10, 0), fill="x")

        self.name_lbl = tk.Label(left, text="", bg=theme.SURFACE, fg=theme.TEXT,
                                  font=(theme.FONT_FAMILY, 13, "bold"), wraplength=200)
        self.name_lbl.pack(pady=(14, 0))
        self.sid_lbl = tk.Label(left, text="", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                 font=(theme.FONT_FAMILY, 9))
        self.sid_lbl.pack()

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        info = ttk.LabelFrame(right, text="Account Information", style="Card.TLabelframe", padding=14)
        info.pack(fill="x", pady=(0, 14))

        ttk.Label(info, text="Full Name:").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.name_entry = ttk.Entry(info, width=32)
        self.name_entry.grid(row=0, column=1, padx=4, pady=6)

        ttk.Label(info, text="Email:").grid(row=0, column=2, sticky="w", padx=4, pady=6)
        self.email_entry = ttk.Entry(info, width=32)
        self.email_entry.grid(row=0, column=3, padx=4, pady=6)

        ttk.Label(info, text="Student ID:").grid(row=1, column=0, sticky="w", padx=4, pady=6)
        self.sid_value_lbl = ttk.Label(info, text="", style="OnCardMuted.TLabel")
        self.sid_value_lbl.grid(row=1, column=1, sticky="w", padx=4)

        ttk.Label(info, text="Card Expiry:").grid(row=1, column=2, sticky="w", padx=4, pady=6)
        self.expiry_value_lbl = ttk.Label(info, text="", style="OnCardMuted.TLabel")
        self.expiry_value_lbl.grid(row=1, column=3, sticky="w", padx=4)

        ttk.Label(info, text="Barcode No.:").grid(row=2, column=0, sticky="w", padx=4, pady=6)
        self.barcode_value_lbl = ttk.Label(info, text="", style="OnCardMuted.TLabel")
        self.barcode_value_lbl.grid(row=2, column=1, sticky="w", padx=4)

        ttk.Label(info, text="Student ID, card expiry, and barcode number are set from your ID "
                              "card and can only be changed by facilities staff.",
                  style="Muted.TLabel", wraplength=480, justify="left").grid(
            row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 0))

        ttk.Button(info, text="Save Changes", style="Primary.TButton",
                   command=self.save_profile).grid(row=4, column=3, sticky="e", padx=4, pady=(12, 0))

        pw = ttk.LabelFrame(right, text="Change Password", style="Card.TLabelframe", padding=14)
        pw.pack(fill="x")
        ttk.Label(pw, text="Current Password:").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.cur_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.cur_pw_entry.grid(row=0, column=1, padx=4, pady=6)
        ttk.Label(pw, text="New Password:").grid(row=1, column=0, sticky="w", padx=4, pady=6)
        self.new_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.new_pw_entry.grid(row=1, column=1, padx=4, pady=6)
        ttk.Label(pw, text="Confirm New Password:").grid(row=2, column=0, sticky="w", padx=4, pady=6)
        self.confirm_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.confirm_pw_entry.grid(row=2, column=1, padx=4, pady=6)
        self.pw_status_lbl = ttk.Label(pw, text="", style="Muted.TLabel")
        self.pw_status_lbl.grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(pw, text="Update Password", style="Primary.TButton",
                   command=self.change_password).grid(row=1, column=2, padx=10)

    def refresh(self):
        user = self.app.user_mgr.get_user(self.app.student_id)
        if user is None:
            return
        self._user = user
        self.name_lbl.configure(text=user["name"])
        self.sid_lbl.configure(text=user["student_id"])
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, user["name"])
        self.email_entry.delete(0, "end")
        self.email_entry.insert(0, user["email"])
        self.sid_value_lbl.configure(text=user["student_id"])
        self.expiry_value_lbl.configure(text=user["expiry_date"])
        self.barcode_value_lbl.configure(text=user["barcode_number"])
        self._render_picture(user["profile_picture"])

    def _render_picture(self, path):
        self.pic_canvas.delete("all")
        try:
            if not path or not os.path.exists(path):
                raise FileNotFoundError
            from PIL import Image, ImageTk
            img = Image.open(path).resize((self.PIC_SIZE, self.PIC_SIZE), Image.LANCZOS)
            self._pic_photo = ImageTk.PhotoImage(img)
            self.pic_canvas.create_image(0, 0, anchor="nw", image=self._pic_photo)
        except Exception:
            self.pic_canvas.create_rectangle(0, 0, self.PIC_SIZE, self.PIC_SIZE,
                                              fill=theme.NEUTRAL, outline="")
            words = (self._user["name"].split() if self._user else [])[:2]
            initials = "".join(w[0] for w in words).upper() if words else "?"
            self.pic_canvas.create_text(self.PIC_SIZE / 2, self.PIC_SIZE / 2, text=initials,
                                         font=(theme.FONT_FAMILY, 34, "bold"), fill=theme.MUTED_TEXT)

    def change_photo(self):
        path = filedialog.askopenfilename(
            title="Choose a profile photo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")])
        if not path:
            return
        try:
            from PIL import Image
            base_dir = Path(__file__).resolve().parent
            pics_dir = base_dir / "assets" / "profile_pics"
            pics_dir.mkdir(parents=True, exist_ok=True)
            dest = pics_dir / f"user_{self.app.student_id}.png"
            img = Image.open(path).convert("RGB")
            # Crop to a centered square first so odd aspect-ratio photos
            # still fill the avatar slot without distortion.
            w, h = img.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side)).resize((300, 300), Image.LANCZOS)
            img.save(dest, "PNG")
        except Exception as exc:
            messagebox.showerror("Photo error", f"Could not use that image:\n{exc}")
            return
        self.app.user_mgr.update_profile_picture(self.app.student_id, str(dest))
        self.refresh()

    def save_profile(self):
        name = self.name_entry.get().strip()
        email = self.email_entry.get().strip()
        if not name or not email:
            messagebox.showwarning("Missing info", "Name and email cannot be empty.")
            return
        try:
            self.app.user_mgr.update_user(self.app.student_id, name=name, email=email)
        except ValueError as exc:
            messagebox.showerror("Profile error", str(exc))
            return
        self.toast("Your profile has been updated.")
        self.refresh()

    def change_password(self):
        current = self.cur_pw_entry.get()
        new = self.new_pw_entry.get()
        confirm_new = self.confirm_pw_entry.get()
        if not self.app.user_mgr.verify_password(self.app.student_id, current):
            self.pw_status_lbl.configure(text="Current password is incorrect.", foreground=theme.DANGER)
            return
        if new != confirm_new:
            self.pw_status_lbl.configure(text="New passwords do not match.", foreground=theme.DANGER)
            return
        try:
            self.app.user_mgr.set_password(self.app.student_id, new)
        except ValueError as exc:
            self.pw_status_lbl.configure(text=str(exc), foreground=theme.DANGER)
            return
        self.cur_pw_entry.delete(0, "end")
        self.new_pw_entry.delete(0, "end")
        self.confirm_pw_entry.delete(0, "end")
        self.pw_status_lbl.configure(text="Password updated successfully.", foreground=theme.SUCCESS)


# ==========================================================================
# Admin's own profile tab - photo, account info, change-password
# ==========================================================================
class AdminProfileTab(BaseTab):
    """
    Self-service profile for the signed-in admin/staff account: upload a
    profile photo and change their own password (current password required).
    Mirrors StudentProfileTab's layout for visual consistency across the app.
    """
    PIC_SIZE = 140

    def _build_ui(self):
        self._page_header("My Profile", "View your account, update your photo, and manage your password.")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left_outer, left_card = shadow_wrap(body)
        left_outer.pack(side="left", fill="y", padx=(0, 16))
        left = tk.Frame(left_card, bg=theme.SURFACE, width=220)
        left.pack(fill="both", expand=True, padx=18, pady=18)

        self.pic_canvas = tk.Canvas(left, width=self.PIC_SIZE, height=self.PIC_SIZE,
                                     highlightthickness=0, bg=theme.NEUTRAL)
        self.pic_canvas.pack()
        ttk.Button(left, text="Change Photo", style="Neutral.TButton",
                   command=self.change_photo).pack(pady=(10, 0), fill="x")

        self.name_lbl = tk.Label(left, text="", bg=theme.SURFACE, fg=theme.TEXT,
                                  font=(theme.FONT_FAMILY, 13, "bold"), wraplength=200)
        self.name_lbl.pack(pady=(14, 0))
        self.role_lbl = tk.Label(left, text="Administrator", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                  font=(theme.FONT_FAMILY, 9))
        self.role_lbl.pack()

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        info = ttk.LabelFrame(right, text="Account Information", style="Card.TLabelframe", padding=14)
        info.pack(fill="x", pady=(0, 14))
        ttk.Label(info, text="Username:").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.username_lbl = ttk.Label(info, text="", style="OnCardHeading.TLabel")
        self.username_lbl.grid(row=0, column=1, sticky="w", padx=4, pady=6)
        ttk.Label(info, text="Account Created:").grid(row=0, column=2, sticky="w", padx=4, pady=6)
        self.created_lbl = ttk.Label(info, text="", style="OnCardMuted.TLabel")
        self.created_lbl.grid(row=0, column=3, sticky="w", padx=4, pady=6)
        ttk.Label(info, text="Usernames identify staff accounts and can't be changed here - "
                              "contact another admin if yours needs to change.",
                  style="Muted.TLabel", wraplength=480, justify="left").grid(
            row=1, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 0))

        pw = ttk.LabelFrame(right, text="Change Password", style="Card.TLabelframe", padding=14)
        pw.pack(fill="x")
        ttk.Label(pw, text="Current Password:").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.cur_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.cur_pw_entry.grid(row=0, column=1, padx=4, pady=6)
        ttk.Label(pw, text="New Password:").grid(row=1, column=0, sticky="w", padx=4, pady=6)
        self.new_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.new_pw_entry.grid(row=1, column=1, padx=4, pady=6)
        ttk.Label(pw, text="Confirm New Password:").grid(row=2, column=0, sticky="w", padx=4, pady=6)
        self.confirm_pw_entry = ttk.Entry(pw, show="\u2022", width=24)
        self.confirm_pw_entry.grid(row=2, column=1, padx=4, pady=6)
        self.pw_status_lbl = ttk.Label(pw, text="", style="Muted.TLabel")
        self.pw_status_lbl.grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(pw, text="Update Password", style="Primary.TButton",
                   command=self.change_password).grid(row=1, column=2, padx=10)

    def refresh(self):
        admin = self.app.auth_mgr.get_admin(self.app.current_admin)
        if admin is None:
            return
        self._admin = admin
        self.name_lbl.configure(text=admin["username"])
        self.username_lbl.configure(text=admin["username"])
        self.created_lbl.configure(text=(admin["created_at"] or "")[:10])
        self._render_picture(admin["profile_picture"] if "profile_picture" in admin.keys() else None)

    def _render_picture(self, path):
        self.pic_canvas.delete("all")
        custom = path if path else None
        avatar_path = assets.get_avatar("admin", self.app.current_admin, self.app.current_admin,
                                         role="Admin", custom_path=custom)
        from PIL import Image, ImageTk
        img = Image.open(avatar_path).resize((self.PIC_SIZE, self.PIC_SIZE), Image.LANCZOS)
        self._pic_photo = ImageTk.PhotoImage(img)
        self.pic_canvas.create_image(0, 0, anchor="nw", image=self._pic_photo)

    def change_photo(self):
        path = filedialog.askopenfilename(
            title="Choose a profile photo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp")])
        if not path:
            return
        try:
            saved_path = assets.save_profile_photo("admin", self.app.current_admin, path)
        except Exception as exc:
            messagebox.showerror("Photo error", f"Could not use that image:\n{exc}")
            return
        self.app.auth_mgr.update_profile_picture(self.app.current_admin, saved_path)
        self.refresh()

    def change_password(self):
        current = self.cur_pw_entry.get()
        new = self.new_pw_entry.get()
        confirm_new = self.confirm_pw_entry.get()
        if not self.app.auth_mgr.verify_login(self.app.current_admin, current):
            self.pw_status_lbl.configure(text="Current password is incorrect.", foreground=theme.DANGER)
            return
        if len(new.strip()) < 6:
            self.pw_status_lbl.configure(text="New password must be at least 6 characters.",
                                          foreground=theme.DANGER)
            return
        if new != confirm_new:
            self.pw_status_lbl.configure(text="New passwords do not match.", foreground=theme.DANGER)
            return
        self.app.auth_mgr.change_password(self.app.current_admin, new)
        self.cur_pw_entry.delete(0, "end")
        self.new_pw_entry.delete(0, "end")
        self.confirm_pw_entry.delete(0, "end")
        self.pw_status_lbl.configure(text="Password updated successfully.", foreground=theme.SUCCESS)

