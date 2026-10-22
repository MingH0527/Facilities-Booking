"""
booking_facilities.py
Facility Booking System - module 3: Booking Facilities
-----------------------------------------------------
Making a booking, and the facility records a booking is made against:

  Verify Member Details      - the requester is resolved against the member
                               list before a booking is accepted
  Check Facility Availability- clash detection, the day timeline and the
                               availability screen
  Record Booking Details     - the booking forms (admin and student)
  Update Database            - writes through the booking manager

Also holds the facility master records (FacilityTab) and the usage and
maintenance screen (MaintenanceTab), since both are the facility side of
what is being booked.

BookingTab and StudentBookingTab pull their approve/decline and
amend/cancel behaviour in from the modules that own those steps.
"""


import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date, datetime

import theme
import assets
from widgets import (ImageCarousel, restripe, confirm, shadow_wrap, DateEntry, EmptyState,
                    BigCalendar, TimeSlotTimeline, DateTimeRangePicker)

from facility_booking_system import (BaseTab, tag_for_status, tag_for_condition,
                                    facility_caption)
from approve_decline_application import ApproveDeclineMixin
from amend_cancel_booking import AdminAmendCancelMixin, StudentAmendCancelMixin


# ==========================================================================
# Reusable booking tab (used for Room / Sports / Equipment - modules a,b,c)
# ==========================================================================
class BookingTab(ApproveDeclineMixin, AdminAmendCancelMixin, BaseTab):
    def __init__(self, master, app, category, type_options):
        self.category = category
        self.type_options = type_options
        super().__init__(master, app)

    # ---------------- UI construction ----------------
    def _build_ui(self):
        self._page_header(f"{self.category} Bookings",
                           f"Submit, approve, reschedule and track {self.category.lower()} bookings.")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        preview_outer, preview_card = shadow_wrap(body)
        preview_outer.pack(side="right", fill="y", padx=(14, 0))
        right = tk.Frame(preview_card, bg=theme.SURFACE, width=220)
        right.pack(fill="both", expand=True, padx=14, pady=14)
        right.pack_propagate(False)
        tk.Label(right, text="SELECTED FACILITY", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w")
        self.preview_canvas = tk.Canvas(right, width=200, height=100, highlightthickness=0,
                                         bg=theme.NEUTRAL)
        self.preview_canvas.pack(pady=(8, 8))
        self.preview_name = tk.Label(right, text="No facility selected", bg=theme.SURFACE,
                                      fg=theme.TEXT, font=(theme.FONT_FAMILY, 11, "bold"),
                                      wraplength=200, justify="left")
        self.preview_name.pack(anchor="w")
        self.preview_info = tk.Label(right, text="", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                      font=(theme.FONT_FAMILY, 9), wraplength=200, justify="left")
        self.preview_info.pack(anchor="w", pady=(4, 0))

        tk.Frame(right, bg=theme.BORDER, height=1).pack(fill="x", pady=12)

        cal_header = tk.Frame(right, bg=theme.SURFACE)
        cal_header.pack(fill="x")
        tk.Label(cal_header, text="BOOKING CALENDAR", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(side="left", anchor="w")
        self.cal_clear_lbl = tk.Label(cal_header, text="Show all", bg=theme.SURFACE, fg=theme.PRIMARY,
                                       font=(theme.FONT_FAMILY, 8, "underline"), cursor="hand2")
        self.cal_clear_lbl.bind("<Button-1>", lambda e: self._clear_calendar_filter())
        self.cal_clear_lbl.pack(side="right")
        self.cal_clear_lbl.pack_forget()  # only shown once a date filter is active

        self._calendar_filter_date = None
        self.booking_calendar = BigCalendar(right, on_pick=self._on_calendar_date_pick)
        self.booking_calendar.pack(pady=(6, 4))
        tk.Label(right, text="Dates with a dot have bookings \u2014 click one to filter the table below.",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 8),
                 wraplength=200, justify="left").pack(anchor="w")

        form = ttk.LabelFrame(left, text=f"New {self.category} Booking Request",
                               style="Card.TLabelframe", padding=12)
        form.pack(fill="x", pady=(0, 10))

        picker_row = tk.Frame(form, bg=theme.SURFACE)
        picker_row.pack(fill="x", pady=(0, 12))
        ttk.Label(picker_row, text="Facility:").pack(side="left")
        self.facility_cb = ttk.Combobox(picker_row, state="readonly", width=28)
        self.facility_cb.pack(side="left", padx=(6, 18))
        self.facility_cb.bind("<<ComboboxSelected>>", lambda e: self._on_facility_change())

        ttk.Label(picker_row, text="Requested by:").pack(side="left")
        self.user_cb = ttk.Combobox(picker_row, state="readonly", width=22)
        self.user_cb.pack(side="left", padx=(6, 0))

        self.picker = DateTimeRangePicker(form, timeline_height=220)
        self.picker.pack(fill="both", expand=True)
        self.picker.set_booked_provider(self._booked_ranges_for)

        purpose_row = tk.Frame(form, bg=theme.SURFACE)
        purpose_row.pack(fill="x", pady=(10, 0))
        ttk.Label(purpose_row, text="Purpose:").pack(side="left")
        self.purpose_entry = ttk.Entry(purpose_row)
        self.purpose_entry.pack(side="left", fill="x", expand=True, padx=(8, 10))
        ttk.Button(purpose_row, text="Submit Request", style="Primary.TButton",
                   command=self.submit_booking).pack(side="right")

        # ---- filter bar ----
        filter_bar = ttk.Frame(left)
        filter_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(filter_bar, text="Filter status:").pack(side="left")
        self.status_filter = ttk.Combobox(
            filter_bar, state="readonly", width=12,
            values=["All", "Pending", "Approved", "Cancelled", "Completed"]
        )
        self.status_filter.set("All")
        self.status_filter.pack(side="left", padx=4)
        self.status_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(filter_bar, text="Search:").pack(side="left", padx=(12, 0))
        self.search_entry = ttk.Entry(filter_bar, width=20)
        self.search_entry.pack(side="left", padx=4)
        ttk.Button(filter_bar, text="Search", style="Neutral.TButton",
                   command=self.refresh).pack(side="left", padx=(4, 0))
        ttk.Button(filter_bar, text="Refresh", style="Neutral.TButton",
                   command=self.refresh).pack(side="left", padx=6)
        self.result_lbl = ttk.Label(filter_bar, style="Muted.TLabel", text="")
        self.result_lbl.pack(side="right")

        # ---- table ----
        table_wrap = ttk.Frame(left, style="Surface.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("id", "facility", "user", "date", "start", "end", "purpose", "status")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=12)
        headers = ["ID", "Facility", "Requested By", "Date", "Start", "End", "Purpose", "Status"]
        widths = [40, 130, 120, 90, 60, 60, 220, 90]
        for c, h, w in zip(columns, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c != "purpose" else "w")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)
        self._empty_state = EmptyState(
            table_wrap, icon="\U0001F4C5", title=f"No {self.category.lower()} bookings found",
            subtitle="Try clearing the filter/search above, or submit a new request.")

        # ---- action buttons ----
        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Approve", style="Success.TButton",
                   command=lambda: self.change_status("Approved")).pack(side="left", padx=4)
        ttk.Button(actions, text="Complete", style="Neutral.TButton",
                   command=lambda: self.change_status("Completed")).pack(side="left", padx=4)
        ttk.Button(actions, text="Cancel Booking", style="Danger.TButton",
                   command=lambda: self.change_status("Cancelled")).pack(side="left", padx=4)
        ttk.Button(actions, text="Reschedule", style="Neutral.TButton",
                   command=self.reschedule_selected).pack(side="left", padx=4)

    # ---------------- data helpers ----------------
    def _facility_map(self):
        facilities = self.app.facility_mgr.list_facilities(self.category)
        self._facility_rows = {f["id"]: f for f in facilities}
        self._facilities = {f"{f['name']} ({f['type']})": f["id"] for f in facilities}
        self.facility_cb["values"] = list(self._facilities.keys())

    def _user_map(self):
        users = self.app.user_mgr.list_users()
        self._users = {f"{u['name']} [{u['role']}]": u["id"] for u in users}
        self.user_cb["values"] = list(self._users.keys())

    def _on_calendar_date_pick(self, picked_date):
        self._calendar_filter_date = picked_date.isoformat()
        self.cal_clear_lbl.pack(side="right")
        self._apply_filters()

    def _clear_calendar_filter(self):
        self._calendar_filter_date = None
        self.cal_clear_lbl.pack_forget()
        self._apply_filters()

    def _on_facility_change(self):
        self._update_preview()
        if hasattr(self, "picker"):
            self.picker.refresh_booked()

    def _booked_ranges_for(self, target_date):
        label = self.facility_cb.get()
        if not label or label not in getattr(self, "_facilities", {}):
            ranges = []
        else:
            fid = self._facilities[label]
            ranges = [
                (b["start_time"], b["end_time"])
                for b in self.app.booking_mgr.list_bookings(None, None, None)
                if b["facility_id"] == fid and b["booking_date"] == target_date
                and b["status"] in ("Pending", "Approved")
            ]
        if target_date == date.today().isoformat():
            ranges.append(("00:00", datetime.now().strftime("%H:%M")))
        return ranges

    def _update_preview(self):
        label = self.facility_cb.get()
        self.preview_canvas.delete("all")
        if not label or label not in self._facilities:
            self.preview_name.configure(text="No facility selected")
            self.preview_info.configure(text="")
            return
        f = self._facility_rows[self._facilities[label]]
        try:
            from PIL import Image, ImageTk
            path = assets.get_facility_card(f)
            img = Image.open(path).resize((200, 100))
            self._preview_photo = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(0, 0, anchor="nw", image=self._preview_photo)
        except Exception:
            self.preview_canvas.create_rectangle(0, 0, 200, 115, fill=theme.NEUTRAL, outline="")
        self.preview_name.configure(text=f["name"])
        self.preview_info.configure(
            text=f"{f['type']} • {f['location'] or 'Unassigned'}\nCapacity {f['capacity']} • {f['condition']}"
        )

    def refresh(self):
        self._facility_map()
        self._user_map()
        status = self.status_filter.get()
        text = self.search_entry.get().strip()
        self._rows = self.app.booking_mgr.list_bookings(self.category, status, text)
        self.booking_calendar.set_marked_dates(
            date.fromisoformat(b["booking_date"]) for b in self._rows
        )
        self._update_preview()
        if hasattr(self, "picker"):
            self.picker.refresh_booked()
        self._apply_filters()

    def _apply_filters(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        rows = self._rows
        if self._calendar_filter_date:
            rows = [b for b in rows if b["booking_date"] == self._calendar_filter_date]
        for b in rows:
            self.tree.insert("", "end", iid=b["id"], values=(
                b["id"], b["facility_name"], b["user_name"], b["booking_date"],
                b["start_time"], b["end_time"], b["purpose"] or "", b["status"]
            ), tags=(tag_for_status(b["status"]),))
        restripe(self.tree)
        count = len(rows)
        if self._calendar_filter_date:
            self.result_lbl.configure(
                text=f"{count} booking{'s' if count != 1 else ''} on {self._calendar_filter_date}")
        else:
            self.result_lbl.configure(text=f"{count} booking{'s' if count != 1 else ''}")
        if count:
            self._empty_state.hide()
        else:
            self._empty_state.show()

    def submit_booking(self):
        fac_label = self.facility_cb.get()
        user_label = self.user_cb.get()
        booking_date, start_time, end_time = self.picker.get_selection()
        purpose = self.purpose_entry.get().strip()
        if not (fac_label and user_label):
            messagebox.showwarning("Missing info", "Please choose a facility and requester first.")
            return
        if not (start_time and end_time):
            messagebox.showwarning(
                "Missing info",
                "Please click a time slot on the timeline (click a second slot to pick a range).",
            )
            return
        if not purpose:
            messagebox.showwarning("Missing info", "Please enter a purpose for this booking.")
            return
        details = (
            f"Facility: {fac_label}\nRequested by: {user_label}\n"
            f"Date: {booking_date}\n"
            f"Time: {start_time} - {end_time}\n\n"
            "Submit this booking request?"
        )
        if not confirm("Confirm Booking Request", details):
            return
        try:
            self.app.booking_mgr.create_booking(
                self._facilities[fac_label],
                self._users[user_label],
                booking_date,
                start_time,
                end_time,
                purpose,
            )
            self.toast("Booking request submitted (status: Pending).")
            self.purpose_entry.delete(0, "end")
            self.refresh()
            self.app.refresh_dashboard()
        except ValueError as e:
            messagebox.showerror("Booking error", str(e))

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Please select a booking first.")
            return None
        return int(sel[0])

# ==========================================================================
# Facility & Resource Management tab (module d)
# ==========================================================================
class FacilityTab(BaseTab):
    def _build_ui(self):
        self._selected_facility_id = None
        self._page_header("Facility & Resource Management",
                           "Add, update, and retire rooms, sports venues and equipment.")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        preview_outer, preview_card = shadow_wrap(body)
        preview_outer.pack(side="right", fill="y", padx=(14, 0))
        right = tk.Frame(preview_card, bg=theme.SURFACE)
        right.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(right, text="PREVIEW", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.carousel = ImageCarousel(right, width=280, height=140, autoplay_ms=0,
                                       on_select=self._select_from_carousel)
        self.carousel.pack()
        self.image_status_label = tk.Label(right, text="No facility selected", bg=theme.SURFACE,
                                           fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 8),
                                           wraplength=260, justify="left")
        self.image_status_label.pack(anchor="w", pady=(8, 0))

        form = ttk.LabelFrame(left, text="Add / Update Facility Master Record",
                               style="Card.TLabelframe", padding=12)
        form.pack(fill="x", pady=(0, 10))

        ttk.Label(form, text="Name:").grid(row=0, column=0, padx=4, pady=5, sticky="w")
        self.name_entry = ttk.Entry(form, width=20)
        self.name_entry.grid(row=0, column=1, padx=4, pady=5)

        ttk.Label(form, text="Category:").grid(row=0, column=2, padx=4, pady=5, sticky="w")
        self.cat_cb = ttk.Combobox(form, state="readonly", width=12, values=["Room", "Sports", "Equipment"])
        self.cat_cb.current(0)
        self.cat_cb.grid(row=0, column=3, padx=4, pady=5)

        ttk.Label(form, text="Type:").grid(row=0, column=4, padx=4, pady=5, sticky="w")
        self.type_entry = ttk.Entry(form, width=16)
        self.type_entry.grid(row=0, column=5, padx=4, pady=5)

        ttk.Label(form, text="Capacity:").grid(row=1, column=0, padx=4, pady=5, sticky="w")
        self.cap_entry = ttk.Entry(form, width=8)
        self.cap_entry.insert(0, "0")
        self.cap_entry.grid(row=1, column=1, padx=4, pady=5, sticky="w")

        ttk.Label(form, text="Location:").grid(row=1, column=2, padx=4, pady=5, sticky="w")
        self.loc_entry = ttk.Entry(form, width=20)
        self.loc_entry.grid(row=1, column=3, padx=4, pady=5)

        ttk.Label(form, text="Condition:").grid(row=1, column=4, padx=4, pady=5, sticky="w")
        self.cond_cb = ttk.Combobox(form, state="readonly", width=16,
                                     values=["Good", "Fair", "Under Maintenance", "Out of Service"])
        self.cond_cb.current(0)
        self.cond_cb.grid(row=1, column=5, padx=4, pady=5)

        btns = ttk.Frame(form)
        btns.grid(row=2, column=0, columnspan=6, pady=8)
        ttk.Button(btns, text="Add New Facility", style="Primary.TButton",
                   command=self.add_facility).pack(side="left", padx=4)
        ttk.Button(btns, text="Update Selected Details", style="Neutral.TButton",
                   command=self.update_selected_facility).pack(side="left", padx=4)
        ttk.Button(btns, text="Upload Picture", style="Success.TButton",
                   command=self.upload_picture).pack(side="left", padx=4)
        ttk.Button(btns, text="Delete Selected", style="Danger.TButton",
                   command=self.delete_facility).pack(side="left", padx=4)

        table_header = ttk.Frame(left)
        table_header.pack(fill="x", pady=(0, 4))
        self.result_lbl = ttk.Label(table_header, style="Muted.TLabel", text="")
        self.result_lbl.pack(side="right")

        table_wrap = ttk.Frame(left, style="Surface.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("id", "name", "category", "type", "capacity", "location", "condition", "status")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=14)
        headers = ["ID", "Name", "Category", "Type", "Cap.", "Location", "Condition", "Status"]
        widths = [40, 130, 90, 110, 50, 130, 120, 90]
        for c, h, w in zip(columns, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._empty_state = EmptyState(
            table_wrap, icon="\U0001F3E2", title="No facilities yet",
            subtitle="Add your first room, sports venue, or equipment using the form above.")

    def _on_select(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        f = self.app.facility_mgr.get_facility(int(sel[0]))
        if f is None:
            return
        self._selected_facility_id = f["id"]
        self._fill_form(f)
        image_path = f["image_path"] if "image_path" in f.keys() else ""
        self.image_status_label.configure(
            text="Custom picture uploaded" if image_path else "Using generated preview"
        )
        self.cond_cb.set(f["condition"])
        if f["id"] in self._id_to_slide:
            self.carousel.go_to(self._id_to_slide[f["id"]])

    def _fill_form(self, facility):
        self.name_entry.delete(0, "end"); self.name_entry.insert(0, facility["name"])
        self.cat_cb.set(facility["category"])
        self.type_entry.delete(0, "end"); self.type_entry.insert(0, facility["type"])
        self.cap_entry.delete(0, "end"); self.cap_entry.insert(0, str(facility["capacity"]))
        self.loc_entry.delete(0, "end"); self.loc_entry.insert(0, facility["location"])
        self.cond_cb.set(facility["condition"])

    def _select_from_carousel(self, index):
        if index < len(self._slide_ids):
            fid = self._slide_ids[index]
            if self.tree.exists(fid):
                self.tree.selection_set(fid)
                self.tree.see(fid)

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        facilities = self.app.facility_mgr.list_facilities()
        for f in facilities:
            self.tree.insert("", "end", iid=f["id"], values=(
                f["id"], f["name"], f["category"], f["type"], f["capacity"],
                f["location"], f["condition"], f["status"]
            ), tags=(tag_for_condition(f["condition"]),))
        restripe(self.tree)
        count = len(facilities)
        self.result_lbl.configure(text=f"{count} facilit{'y' if count == 1 else 'ies'}")
        if count:
            self._empty_state.hide()
        else:
            self._empty_state.show()

        paths = [assets.get_facility_card(f) for f in facilities]
        captions = [facility_caption(f) for f in facilities]
        self._slide_ids = [f["id"] for f in facilities]
        self._id_to_slide = {fid: i for i, fid in enumerate(self._slide_ids)}
        self.carousel.set_slides(paths, captions)

    def add_facility(self):
        name = self.name_entry.get().strip()
        ftype = self.type_entry.get().strip()
        location = self.loc_entry.get().strip()
        if not name or not ftype or not location:
            messagebox.showwarning("Missing info", "Name, Type, and Location are required.")
            return
        try:
            cap = int(self.cap_entry.get().strip() or 0)
        except ValueError:
            messagebox.showerror("Invalid", "Capacity must be a number.")
            return
        summary = (f"Add new facility '{name}' ({self.cat_cb.get()} - {ftype}), "
                   f"capacity {cap}, at {self.loc_entry.get().strip() or 'Unassigned'}?")
        if not confirm("Confirm Add Facility", summary):
            return
        try:
            self.app.facility_mgr.add_facility(
                name, self.cat_cb.get(), ftype, cap, location, self.cond_cb.get()
            )
        except ValueError as exc:
            messagebox.showerror("Invalid data", str(exc))
            return
        self.toast(f"Facility '{name}' added.")
        self.name_entry.delete(0, "end"); self.type_entry.delete(0, "end"); self.loc_entry.delete(0, "end")
        self.refresh()
        self.app.refresh_all_booking_tabs()
        self.app.refresh_dashboard()

    def update_selected_facility(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a facility first.")
            return
        f = self.app.facility_mgr.get_facility(int(sel[0]))
        name = self.name_entry.get().strip()
        category = self.cat_cb.get().strip()
        ftype = self.type_entry.get().strip()
        location = self.loc_entry.get().strip()
        condition = self.cond_cb.get().strip()
        if not all((name, category, ftype, location, condition)):
            messagebox.showwarning("Missing info", "Name, category, type, location, and condition are required.")
            return
        try:
            cap = int(self.cap_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid", "Capacity must be a number.")
            return
        if not confirm("Confirm Facility Update", f"Update details for '{f['name']}'?"):
            return
        status = "Maintenance" if condition in ("Under Maintenance", "Out of Service") else "Available"
        self.app.facility_mgr.update_facility(
            int(sel[0]),
            name=name,
            category=category,
            type=ftype,
            capacity=cap,
            location=location,
            condition=condition,
            status=status,
        )
        self.refresh()
        self.tree.selection_set(sel[0])
        self.tree.see(sel[0])
        self.app.refresh_all_booking_tabs()
        self.app.refresh_dashboard()

    def upload_picture(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a facility or resource first.")
            return
        f = self.app.facility_mgr.get_facility(int(sel[0]))
        path = filedialog.askopenfilename(
            title=f"Choose picture for {f['name']}",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            saved_path = assets.save_facility_image(f["id"], path)
            self.app.facility_mgr.update_facility(f["id"], image_path=saved_path)
        except Exception as exc:
            messagebox.showerror("Upload failed", str(exc))
            return
        self.toast(f"Picture updated for '{f['name']}'.")
        self.refresh()
        self.tree.selection_set(f["id"])
        self.tree.see(f["id"])
        self.app.refresh_all_booking_tabs()
        self.app.refresh_dashboard()

    def delete_facility(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a facility first.")
            return
        f = self.app.facility_mgr.get_facility(int(sel[0]))
        if confirm("Delete Facility",
                   f"Delete '{f['name']}' and all its related bookings/logs? "
                   "This cannot be undone.", danger=True):
            self.app.facility_mgr.delete_facility(int(sel[0]))
            self.refresh()
            self.app.refresh_all_booking_tabs()
            self.app.refresh_dashboard()


# ==========================================================================
# Usage & Maintenance tab (module e)
# ==========================================================================
class MaintenanceTab(BaseTab):
    def _build_ui(self):
        self._page_header("Usage & Maintenance",
                           "Log issues, track repairs, and record check-ins and check-outs.")

        top = ttk.PanedWindow(self, orient="horizontal")
        top.pack(fill="both", expand=True)

        # ---- Maintenance panel ----
        maint_frame = ttk.LabelFrame(top, text="Maintenance Logs", style="Card.TLabelframe", padding=10)
        top.add(maint_frame, weight=1)

        form = ttk.Frame(maint_frame)
        form.pack(fill="x")
        ttk.Label(form, text="Facility:").grid(row=0, column=0, padx=3, pady=4, sticky="w")
        self.facility_cb = ttk.Combobox(form, state="readonly", width=22)
        self.facility_cb.grid(row=0, column=1, padx=3, pady=4)
        ttk.Label(form, text="Reported by:").grid(row=0, column=2, padx=3, pady=4, sticky="w")
        self.reporter_entry = ttk.Entry(form, width=16)
        self.reporter_entry.grid(row=0, column=3, padx=3, pady=4)
        ttk.Label(form, text="Description:").grid(row=1, column=0, padx=3, pady=4, sticky="w")
        self.desc_entry = ttk.Entry(form, width=40)
        self.desc_entry.grid(row=1, column=1, columnspan=3, padx=3, pady=4, sticky="we")
        ttk.Button(form, text="Log Issue", style="Primary.TButton",
                   command=self.log_issue).grid(row=1, column=4, padx=4)

        cols = ("id", "facility", "date", "description", "status")
        maint_table_wrap = ttk.Frame(maint_frame, style="Surface.TFrame")
        maint_table_wrap.pack(fill="both", expand=True, pady=8)
        self.maint_tree = ttk.Treeview(maint_table_wrap, columns=cols, show="headings", height=12)
        for c, h, w in zip(cols, ["ID", "Facility", "Date", "Description", "Status"], [30, 110, 80, 220, 90]):
            self.maint_tree.heading(c, text=h)
            self.maint_tree.column(c, width=w, anchor="center" if c != "description" else "w")
        self.maint_tree.pack(fill="both", expand=True)
        self._setup_tree(self.maint_tree)
        self._maint_empty = EmptyState(
            maint_table_wrap, icon="\U0001F527", title="No maintenance logs",
            subtitle="Log an issue using the form above to start tracking repairs.")

        mbtns = ttk.Frame(maint_frame)
        mbtns.pack(fill="x")
        ttk.Button(mbtns, text="Mark In Progress", style="Neutral.TButton",
                   command=lambda: self.set_log_status("In Progress")).pack(side="left", padx=3)
        ttk.Button(mbtns, text="Mark Resolved", style="Success.TButton",
                   command=lambda: self.set_log_status("Resolved")).pack(side="left", padx=3)

        # ---- Usage panel ----
        usage_frame = ttk.LabelFrame(top, text="Usage Logs (Check-in / Check-out)",
                                      style="Card.TLabelframe", padding=10)
        top.add(usage_frame, weight=1)

        uform = ttk.Frame(usage_frame)
        uform.pack(fill="x")
        ttk.Label(uform, text="Facility:").grid(row=0, column=0, padx=3, pady=4, sticky="w")
        self.usage_facility_cb = ttk.Combobox(uform, state="readonly", width=22)
        self.usage_facility_cb.grid(row=0, column=1, padx=3, pady=4)
        ttk.Button(uform, text="Check In", style="Primary.TButton",
                   command=self.check_in).grid(row=0, column=2, padx=4)

        ucols = ("id", "facility", "check_in", "check_out", "notes")
        usage_table_wrap = ttk.Frame(usage_frame, style="Surface.TFrame")
        usage_table_wrap.pack(fill="both", expand=True, pady=8)
        self.usage_tree = ttk.Treeview(usage_table_wrap, columns=ucols, show="headings", height=12)
        for c, h, w in zip(ucols, ["ID", "Facility", "Check In", "Check Out", "Notes"], [30, 110, 140, 140, 120]):
            self.usage_tree.heading(c, text=h)
            self.usage_tree.column(c, width=w, anchor="center")
        self.usage_tree.pack(fill="both", expand=True)
        self._setup_tree(self.usage_tree)
        self._usage_empty = EmptyState(
            usage_table_wrap, icon="\U0001F550", title="No usage logs",
            subtitle="Check in to a facility above to start a usage log.")

        ttk.Button(usage_frame, text="Check Out Selected", style="Neutral.TButton",
                   command=self.check_out).pack(anchor="w")

    def _facility_map(self):
        facilities = self.app.facility_mgr.list_facilities()
        self._facilities = {f"{f['name']} ({f['category']})": f["id"] for f in facilities}
        self.facility_cb["values"] = list(self._facilities.keys())
        self.usage_facility_cb["values"] = list(self._facilities.keys())

    def refresh(self):
        self._facility_map()
        for row in self.maint_tree.get_children():
            self.maint_tree.delete(row)
        maint_logs = self.app.maintenance_mgr.list_logs()
        for m in maint_logs:
            self.maint_tree.insert("", "end", iid=m["id"], values=(
                m["id"], m["facility_name"], m["log_date"], m["description"] or "", m["status"]
            ))
        restripe(self.maint_tree)
        (self._maint_empty.hide if maint_logs else self._maint_empty.show)()

        for row in self.usage_tree.get_children():
            self.usage_tree.delete(row)
        usage_logs = self.app.usage_mgr.list_logs()
        for u in usage_logs:
            self.usage_tree.insert("", "end", iid=u["id"], values=(
                u["id"], u["facility_name"], u["check_in"] or "", u["check_out"] or "", u["notes"] or ""
            ))
        restripe(self.usage_tree)
        (self._usage_empty.hide if usage_logs else self._usage_empty.show)()

    def log_issue(self):
        label = self.facility_cb.get()
        desc = self.desc_entry.get().strip()
        reporter = self.reporter_entry.get().strip()
        if not label or not desc or not reporter:
            messagebox.showwarning("Missing", "Please fill in facility, reporter, and description.")
            return
        if not confirm("Confirm Maintenance Log",
                       f"Log a maintenance issue for '{label}'?\n\n"
                       f"Description: {desc}\nReported by: {reporter}\n\n"
                       "This will mark the facility as 'Under Maintenance'."):
            return
        try:
            self.app.maintenance_mgr.log_issue(self._facilities[label], desc, reporter)
        except ValueError as exc:
            messagebox.showerror("Invalid data", str(exc))
            return
        self.desc_entry.delete(0, "end")
        self.reporter_entry.delete(0, "end")
        self.refresh()
        self.app.refresh_all_booking_tabs()
        self.app.facility_tab.refresh()
        self.app.refresh_dashboard()

    def set_log_status(self, status):
        sel = self.maint_tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a log entry.")
            return
        vals = self.maint_tree.item(sel[0], "values")
        if not confirm(f"Mark as {status}",
                       f"Mark the maintenance log for '{vals[1]}' as '{status}'?"):
            return
        self.app.maintenance_mgr.update_status(int(sel[0]), status)
        self.refresh()
        self.app.facility_tab.refresh()
        self.app.refresh_dashboard()

    def check_in(self):
        label = self.usage_facility_cb.get()
        if not label:
            messagebox.showwarning("Missing", "Choose a facility.")
            return
        if not confirm("Confirm Check-In", f"Check in to '{label}' now?"):
            return
        self.app.usage_mgr.check_in(self._facilities[label])
        self.refresh()

    def check_out(self):
        sel = self.usage_tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Select a usage log entry.")
            return
        vals = self.usage_tree.item(sel[0], "values")
        if not confirm("Confirm Check-Out", f"Check out of '{vals[1]}' now?"):
            return
        self.app.usage_mgr.check_out(int(sel[0]))
        self.refresh()


# ==========================================================================
# Student portal tabs - booking, availability, and self-service profile.
# Deliberately separate from BookingTab/UserTab: a student may only book
# for themselves, browse (not manage) facilities, and edit their own
# profile - never anyone else's record or the facility master data.
# ==========================================================================
class StudentBookingTab(StudentAmendCancelMixin, BaseTab):
    def _build_ui(self):
        self._page_header("Book a Facility",
                           "Reserve a room, sports facility, or piece of equipment for yourself.")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        preview_outer, preview_card = shadow_wrap(body)
        preview_outer.pack(side="right", fill="y", padx=(14, 0))
        right = tk.Frame(preview_card, bg=theme.SURFACE, width=220)
        right.pack(fill="both", expand=True, padx=14, pady=14)
        right.pack_propagate(False)
        tk.Label(right, text="SELECTED FACILITY", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w")
        self.preview_canvas = tk.Canvas(right, width=200, height=100, highlightthickness=0,
                                         bg=theme.NEUTRAL)
        self.preview_canvas.pack(pady=(8, 8))
        self.preview_name = tk.Label(right, text="No facility selected", bg=theme.SURFACE,
                                      fg=theme.TEXT, font=(theme.FONT_FAMILY, 11, "bold"),
                                      wraplength=200, justify="left")
        self.preview_name.pack(anchor="w")
        self.preview_info = tk.Label(right, text="", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                                      font=(theme.FONT_FAMILY, 9), wraplength=200, justify="left")
        self.preview_info.pack(anchor="w", pady=(4, 0))

        tk.Frame(right, bg=theme.BORDER, height=1).pack(fill="x", pady=12)

        tk.Label(right, text="FACILITIES SHOWCASE", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.showcase_carousel = ImageCarousel(right, width=200, height=120, autoplay_ms=4500,
                                                on_select=self._select_from_showcase)
        self.showcase_carousel.pack()
        tk.Label(right, text="Browse what's available - click a photo to select it above.",
                 bg=theme.SURFACE, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 8),
                 wraplength=200, justify="left").pack(anchor="w", pady=(6, 0))

        form = ttk.LabelFrame(left, text="New Booking Request", style="Card.TLabelframe", padding=12)
        form.pack(fill="x", pady=(0, 10))

        picker_row = tk.Frame(form, bg=theme.SURFACE)
        picker_row.pack(fill="x", pady=(0, 12))
        tk.Label(picker_row, text="Category:", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9)).pack(side="left")
        self.category_cb = ttk.Combobox(picker_row, state="readonly", width=14,
                                         values=["Room", "Sports", "Equipment"])
        self.category_cb.set("Room")
        self.category_cb.pack(side="left", padx=(6, 18))
        self.category_cb.bind("<<ComboboxSelected>>", lambda e: self._facility_map())

        tk.Label(picker_row, text="Facility:", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9)).pack(side="left")
        self.facility_cb = ttk.Combobox(picker_row, state="readonly", width=32)
        self.facility_cb.pack(side="left", padx=(6, 0))
        self.facility_cb.bind("<<ComboboxSelected>>", lambda e: self._on_facility_change())

        steps = tk.Frame(form, bg=theme.SURFACE)
        steps.pack(fill="both", expand=True)

        cal_col = tk.Frame(steps, bg=theme.SURFACE)
        cal_col.pack(side="left", padx=(0, 20), anchor="n")
        tk.Label(cal_col, text="1. Pick a date", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9, "bold")).pack(anchor="w", pady=(0, 6))
        self.calendar = BigCalendar(cal_col, on_pick=self._on_date_pick)
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

        self.timeline = TimeSlotTimeline(time_col, on_range_pick=lambda s, e: self._update_selection_label())
        self.timeline.pack(fill="both", expand=True)

        self.selection_lbl = tk.Label(form, text="Select a date and time above to continue.",
                                       bg=theme.SURFACE, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9))
        self.selection_lbl.pack(anchor="w", pady=(10, 0))

        purpose_row = tk.Frame(form, bg=theme.SURFACE)
        purpose_row.pack(fill="x", pady=(8, 0))
        tk.Label(purpose_row, text="Purpose:", bg=theme.SURFACE, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 9)).pack(side="left")
        self.purpose_entry = ttk.Entry(purpose_row)
        self.purpose_entry.pack(side="left", fill="x", expand=True, padx=(8, 10))
        ttk.Button(purpose_row, text="Submit Request", style="Primary.TButton",
                   command=self.submit_booking).pack(side="right")

        ttk.Label(left, text="My Bookings", style="SubHeading.TLabel").pack(anchor="w", pady=(8, 4))

        filter_bar = ttk.Frame(left)
        filter_bar.pack(fill="x", pady=(0, 6))
        ttk.Label(filter_bar, text="Filter status:").pack(side="left")
        self.status_filter = ttk.Combobox(
            filter_bar, state="readonly", width=12,
            values=["All", "Pending", "Approved", "Cancelled", "Completed"]
        )
        self.status_filter.set("All")
        self.status_filter.pack(side="left", padx=4)
        self.status_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(filter_bar, text="Refresh", style="Neutral.TButton",
                   command=self.refresh).pack(side="left", padx=6)

        table_wrap = ttk.Frame(left, style="Surface.TFrame")
        table_wrap.pack(fill="both", expand=True)
        columns = ("id", "facility", "category", "date", "start", "end", "purpose", "status")
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=11)
        headers = ["ID", "Facility", "Category", "Date", "Start", "End", "Purpose", "Status"]
        widths = [40, 150, 90, 90, 60, 60, 220, 90]
        for c, h, w in zip(columns, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c != "purpose" else "w")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)
        self._empty_state = EmptyState(
            table_wrap, icon="\U0001F4C5", title="No bookings yet",
            subtitle="Submit a booking request above to see it show up here.")

        actions = ttk.Frame(left)
        actions.pack(fill="x", pady=8)
        ttk.Button(actions, text="Cancel Booking", style="Danger.TButton",
                   command=self.cancel_selected).pack(side="left", padx=4)
        ttk.Button(actions, text="Reschedule", style="Neutral.TButton",
                   command=self.reschedule_selected).pack(side="left", padx=4)

    # ---------------- data helpers ----------------
    def _facility_map(self):
        category = self.category_cb.get()
        facilities = self.app.facility_mgr.list_facilities(category)
        self._facility_rows = {f["id"]: f for f in facilities}
        self._facilities = {f"{f['name']} ({f['type']})": f["id"] for f in facilities}
        self.facility_cb["values"] = list(self._facilities.keys())
        if self.facility_cb.get() not in self._facilities:
            self.facility_cb.set("")
        self._update_preview()
        self._refresh_timeline()

        paths = [assets.get_facility_card(f) for f in facilities]
        captions = [f["name"] for f in facilities]
        self._showcase_ids = [f["id"] for f in facilities]
        self.showcase_carousel.set_slides(paths, captions)

    def _on_facility_change(self):
        self._update_preview()
        self._refresh_timeline()

    def _on_date_pick(self, _picked_date):
        self._refresh_timeline()

    def _refresh_timeline(self):
        if not hasattr(self, "timeline"):
            return
        self.timeline.clear_selection()
        target_date = self.calendar.get_selected().isoformat()
        past_range = [("00:00", datetime.now().strftime("%H:%M"))] \
            if target_date == date.today().isoformat() else []
        label = self.facility_cb.get()
        if not label or label not in self._facilities:
            self.timeline.set_booked(past_range)
            self._update_selection_label()
            return
        fid = self._facilities[label]
        ranges = [
            (b["start_time"], b["end_time"])
            for b in self.app.booking_mgr.list_bookings(None, None, None)
            if b["facility_id"] == fid and b["booking_date"] == target_date
            and b["status"] in ("Pending", "Approved")
        ]
        self.timeline.set_booked(ranges + past_range)
        self._update_selection_label()

    def _update_selection_label(self):
        s, e = self.timeline.get_range()
        if s and e:
            d = self.calendar.get_selected()
            self.selection_lbl.configure(
                text=f"Selected: {d.strftime('%a, %d %b %Y')}  \u2022  {s} \u2013 {e}",
                fg=theme.PRIMARY)
        else:
            self.selection_lbl.configure(text="Select a date and time above to continue.",
                                          fg=theme.MUTED_TEXT)

    def _select_from_showcase(self, index):
        if index < len(self._showcase_ids):
            fid = self._showcase_ids[index]
            f = self._facility_rows.get(fid)
            if f:
                label = f"{f['name']} ({f['type']})"
                self.facility_cb.set(label)
                self._update_preview()
                self._refresh_timeline()

    def _update_preview(self):
        label = self.facility_cb.get()
        self.preview_canvas.delete("all")
        if not label or label not in self._facilities:
            self.preview_name.configure(text="No facility selected")
            self.preview_info.configure(text="")
            return
        f = self._facility_rows[self._facilities[label]]
        try:
            from PIL import Image, ImageTk
            path = assets.get_facility_card(f)
            img = Image.open(path).resize((200, 100))
            self._preview_photo = ImageTk.PhotoImage(img)
            self.preview_canvas.create_image(0, 0, anchor="nw", image=self._preview_photo)
        except Exception:
            self.preview_canvas.create_rectangle(0, 0, 200, 100, fill=theme.NEUTRAL, outline="")
        self.preview_name.configure(text=f["name"])
        self.preview_info.configure(
            text=f"{f['type']} • {f['location'] or 'Unassigned'}\nCapacity {f['capacity']} • {f['condition']}"
        )

    def refresh(self):
        self._facility_map()
        for row in self.tree.get_children():
            self.tree.delete(row)
        status = self.status_filter.get()
        count = 0
        for b in self.app.booking_mgr.list_bookings(None, status, None):
            if b["user_id"] != self.app.student_id:
                continue
            self.tree.insert("", "end", iid=b["id"], values=(
                b["id"], b["facility_name"], b["category"], b["booking_date"],
                b["start_time"], b["end_time"], b["purpose"] or "", b["status"]
            ), tags=(tag_for_status(b["status"]),))
            count += 1
        restripe(self.tree)
        (self._empty_state.hide if count else self._empty_state.show)()

    def submit_booking(self):
        fac_label = self.facility_cb.get()
        if not fac_label or fac_label not in self._facilities:
            messagebox.showwarning("Missing info", "Please choose a facility first.")
            return
        booking_date = self.calendar.get_selected().isoformat()
        start_time, end_time = self.timeline.get_range()
        if not (start_time and end_time):
            messagebox.showwarning(
                "Missing info",
                "Please click a time slot on the timeline (click a second slot to pick a range).",
            )
            return
        purpose = self.purpose_entry.get().strip()
        if not purpose:
            messagebox.showwarning("Missing info", "Please enter a purpose for this booking.")
            return
        details = (
            f"Facility: {fac_label}\nDate: {booking_date}\n"
            f"Time: {start_time} - {end_time}\n\n"
            "Submit this booking request?"
        )
        if not confirm("Confirm Booking Request", details):
            return
        try:
            self.app.booking_mgr.create_booking(
                self._facilities[fac_label],
                self.app.student_id,
                booking_date,
                start_time,
                end_time,
                purpose,
            )
            self.toast("Booking request submitted (status: Pending).")
            self.purpose_entry.delete(0, "end")
            self._refresh_timeline()
            self.refresh()
        except ValueError as e:
            messagebox.showerror("Booking error", str(e))

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No selection", "Please select one of your bookings first.")
            return None
        return int(sel[0])

class StudentAvailabilityTab(BaseTab):
    def _build_ui(self):
        self._page_header("Check Availability",
                           "See which facilities are free (and when they're booked) for a given date.")

        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 10))
        ttk.Label(bar, text="Category:").pack(side="left")
        self.category_cb = ttk.Combobox(bar, state="readonly", width=14,
                                         values=["All", "Room", "Sports", "Equipment"])
        self.category_cb.set("All")
        self.category_cb.pack(side="left", padx=4)
        ttk.Label(bar, text="Date:").pack(side="left", padx=(12, 0))
        self.date_entry = DateEntry(bar, order="ymd", width=12)
        self.date_entry.insert(0, date.today().isoformat())
        self.date_entry.pack(side="left", padx=4)
        ttk.Button(bar, text="Check Availability", style="Primary.TButton",
                   command=self.refresh).pack(side="left", padx=8)

        columns = ("facility", "category", "type", "location", "capacity", "condition", "booked_slots")
        table_wrap = ttk.Frame(self, style="Surface.TFrame")
        table_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=16)
        headers = ["Facility", "Category", "Type", "Location", "Capacity", "Condition", "Booked Slots"]
        widths = [140, 90, 110, 110, 80, 130, 260]
        for c, h, w in zip(columns, headers, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c != "booked_slots" else "w")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)
        self._empty_state = EmptyState(
            table_wrap, icon="\U0001F3E2", title="No facilities in this category",
            subtitle="Try a different category.")

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        category = self.category_cb.get()
        target_date = self.date_entry.get().strip() or date.today().isoformat()
        facilities = self.app.facility_mgr.list_facilities(category)
        bookings = self.app.booking_mgr.list_bookings(category if category != "All" else None)
        by_facility = {}
        for b in bookings:
            if b["booking_date"] != target_date or b["status"] not in ("Pending", "Approved"):
                continue
            by_facility.setdefault(b["facility_id"], []).append(f"{b['start_time']}-{b['end_time']}")
        for f in facilities:
            slots = sorted(by_facility.get(f["id"], []))
            booked_text = ", ".join(slots) if slots else "Free all day"
            self.tree.insert("", "end", iid=f["id"], values=(
                f["name"], f["category"], f["type"], f["location"] or "Unassigned",
                f["capacity"], f["condition"], booked_text
            ), tags=(tag_for_condition(f["condition"]),))
        restripe(self.tree)
        (self._empty_state.hide if facilities else self._empty_state.show)()

