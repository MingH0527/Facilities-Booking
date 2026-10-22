"""
generate_report.py
Facility Booking System - module 5: Generate Report
---------------------------------------------------
Reading the booking data back out as figures rather than records:

  Create or Export Criteria - the utilisation figures the report is built
                              from, and the CSV export file dialog
  Generate Report           - the report table itself, plus the dashboard
                              overview cards and upcoming-booking list

Both screens are read-only over the managers; nothing here writes.
"""


import csv
import tkinter as tk
from tkinter import ttk, filedialog

import theme
import assets
from widgets import ImageCarousel, restripe, confirm, StatCard, shadow_wrap

from facility_booking_system import APP_TITLE, BaseTab, facility_caption


# ==========================================================================
# Dashboard tab (extra feature)
# ==========================================================================
class DashboardTab(BaseTab):
    PADDING = 16

    def _build_ui(self):
        header_wrap = tk.Frame(self, bg=theme.BG)
        header_wrap.pack(fill="x")
        title_box = tk.Frame(header_wrap, bg=theme.BG)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(title_box, text=APP_TITLE, bg=theme.BG, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 20, "bold")).pack(anchor="w")
        tk.Label(title_box, text="A quick look at everything happening across campus facilities today.",
                 bg=theme.BG, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 10)).pack(anchor="w", pady=(2, 0))
        ttk.Button(header_wrap, text="Refresh", style="Ghost.TButton",
                   command=self.refresh).pack(side="right", anchor="n")
        tk.Frame(self, bg=theme.PRIMARY, height=3).pack(fill="x", pady=(10, 16))

        self.stats_frame = tk.Frame(self, bg=theme.BG)
        self.stats_frame.pack(fill="x")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(16, 0))

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        carousel_outer, carousel_card = shadow_wrap(body)
        carousel_outer.pack(side="right", fill="y", padx=(14, 0))
        right = tk.Frame(carousel_card, bg=theme.SURFACE)
        right.pack(fill="both", expand=True, padx=14, pady=14)
        tk.Label(right, text="FACILITIES SHOWCASE", bg=theme.SURFACE, fg=theme.MUTED_TEXT,
                 font=(theme.FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.carousel = ImageCarousel(right, width=340, height=170)
        self.carousel.pack()

        tk.Label(left, text="Upcoming Approved Bookings (next 3 days)", bg=theme.BG, fg=theme.TEXT,
                  font=(theme.FONT_FAMILY, 12, "bold")).pack(anchor="w", pady=(0, 8))
        cols = ("facility", "user", "date", "start", "end")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=10)
        for c, h in zip(cols, ["Facility", "Requested By", "Date", "Start", "End"]):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=140, anchor="center")
        self.tree.pack(fill="both", expand=True)
        self._setup_tree(self.tree)

    def refresh(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        facilities = self.app.facility_mgr.list_facilities()
        bookings = self.app.booking_mgr.list_bookings()
        pending = sum(1 for b in bookings if b["status"] == "Pending")
        approved = sum(1 for b in bookings if b["status"] == "Approved")
        maintenance = sum(1 for f in facilities if f["condition"] in ("Under Maintenance", "Out of Service"))

        cards = [
            ("\U0001F3E2", "Total Facilities", len(facilities)),
            ("\U0001F4C5", "Total Bookings", len(bookings)),
            ("\u23F3", "Pending Requests", pending),
            ("\u2705", "Approved Bookings", approved),
            ("\U0001F6E0", "Under Maintenance", maintenance),
        ]
        for i, (icon, label, value) in enumerate(cards):
            accent = theme.STAT_ACCENTS[i % len(theme.STAT_ACCENTS)]
            card = StatCard(self.stats_frame, icon, value, label, accent=accent)
            card.outer.grid(row=0, column=i, padx=6, sticky="we")
            self.stats_frame.grid_columnconfigure(i, weight=1)

        for row in self.tree.get_children():
            self.tree.delete(row)
        for b in self.app.booking_mgr.upcoming_bookings(days_ahead=3):
            self.tree.insert("", "end", values=(
                b["facility_name"], b["user_name"], b["booking_date"], b["start_time"], b["end_time"]
            ))
        restripe(self.tree)

        paths = [assets.get_facility_card(f) for f in facilities]
        captions = [facility_caption(f) for f in facilities]
        self.carousel.set_slides(paths, captions)


# ==========================================================================
# Reports tab (extra feature)
# ==========================================================================
class ReportsTab(BaseTab):
    def _build_ui(self):
        self._page_header("Facility Utilization Report",
                           "See booking activity per facility and export records to CSV.")
        cols = ("name", "category", "total", "approved", "cancelled")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        for c, h in zip(cols, ["Facility", "Category", "Total Bookings", "Approved", "Cancelled"]):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=140, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=10)
        self._setup_tree(self.tree)

        btns = ttk.Frame(self)
        btns.pack(fill="x")
        ttk.Button(btns, text="Refresh", style="Neutral.TButton",
                   command=self.refresh).pack(side="left", padx=4)
        ttk.Button(btns, text="Export Bookings to CSV", style="Primary.TButton",
                   command=self.export_csv).pack(side="left", padx=4)

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in self.app.facility_mgr.utilization_report():
            self.tree.insert("", "end", values=(
                r["name"], r["category"], r["total_bookings"] or 0,
                r["approved"] or 0, r["cancelled"] or 0
            ))
        restripe(self.tree)

    def export_csv(self):
        if not confirm("Export Bookings", "Export all bookings to a CSV file?"):
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV files", "*.csv")],
                                             initialfile="bookings_export.csv")
        if not path:
            return
        bookings = self.app.booking_mgr.list_bookings()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["ID", "Facility", "Category", "Requested By", "Date",
                              "Start", "End", "Purpose", "Status"])
            for b in bookings:
                writer.writerow([b["id"], b["facility_name"], b["category"], b["user_name"],
                                  b["booking_date"], b["start_time"], b["end_time"],
                                  b["purpose"], b["status"]])
        self.toast(f"Bookings exported to: {path}")

