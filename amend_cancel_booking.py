"""
amend_cancel_booking.py
Facility Booking System - module 4: Amend or Cancel Booking
-----------------------------------------------------------
Changing or withdrawing a booking that already exists:

  Verify Booking Details            - the selected booking is re-read and
                                      its facility/slot re-checked
  Record Amendment or Cancellation  - the new slot or the cancellation is
                                      written back to the database
  Booking Confirmation / Present    - the reschedule dialog and its confirm
                                      step, plus the resulting toast
  Record Amendment/Cancellation Log - handled by the booking manager's own
                                      status history

Supplied as mixins for the same reason as the approve/decline module: the
behaviour stays on the booking screens at runtime, the code lives here.
AdminAmendCancelMixin is picked up by BookingTab, StudentAmendCancelMixin by
StudentBookingTab.
"""


import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime

import theme
from widgets import confirm, DateTimeRangePicker


class AdminAmendCancelMixin:
    """Reschedule an existing booking from the admin booking screen."""

    def reschedule_selected(self):
        bid = self._selected_id()
        if bid is None:
            return
        booking = self.app.booking_mgr.get_booking(bid)
        if booking is None:
            return
        lock_reason = self.app.booking_mgr.reschedule_lock_reason(booking)
        if lock_reason:
            messagebox.showwarning("Can't reschedule", lock_reason)
            return
        win = tk.Toplevel(self)
        win.title("Reschedule Booking")
        win.configure(bg=theme.BG)
        win.resizable(False, False)

        tk.Label(win, text=f"{booking['facility_name']} \u2014 requested by {booking['user_name']}",
                 bg=theme.BG, fg=theme.TEXT, font=(theme.FONT_FAMILY, 10, "bold")
                 ).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(win, text=f"Currently: {booking['booking_date']}  {booking['start_time']} \u2013 {booking['end_time']}",
                 bg=theme.BG, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9)
                 ).pack(anchor="w", padx=16, pady=(0, 10))

        picker = DateTimeRangePicker(
            win, timeline_height=220,
            initial_date=date.fromisoformat(booking["booking_date"]),
            initial_start=booking["start_time"], initial_end=booking["end_time"])
        picker.pack(padx=16)

        def booked_ranges(target_date):
            ranges = [
                (b["start_time"], b["end_time"])
                for b in self.app.booking_mgr.list_bookings(None, None, None)
                if b["facility_id"] == booking["facility_id"] and b["booking_date"] == target_date
                and b["status"] in ("Pending", "Approved") and b["id"] != bid
            ]
            if target_date == date.today().isoformat():
                ranges.append(("00:00", datetime.now().strftime("%H:%M")))
            return ranges
        picker.set_booked_provider(booked_ranges)

        def confirm_reschedule():
            new_date, new_start, new_end = picker.get_selection()
            if not (new_start and new_end):
                messagebox.showwarning("Missing info", "Please pick a time slot on the timeline.")
                return
            summary = f"Move this booking to {new_date}\n{new_start} \u2013 {new_end}?"
            if not confirm("Confirm Reschedule", summary):
                return
            try:
                self.app.booking_mgr.reschedule(bid, new_date, new_start, new_end)
                self.toast("Booking rescheduled.")
                win.destroy()
                self.refresh()
                self.app.refresh_dashboard()
            except ValueError as ex:
                messagebox.showerror("Error", str(ex))

        ttk.Button(win, text="Confirm", style="Primary.TButton",
                   command=confirm_reschedule).pack(pady=(10, 16))



class StudentAmendCancelMixin:
    """Cancel or reschedule one of the student's own bookings."""

    def cancel_selected(self):
        bid = self._selected_id()
        if bid is None:
            return
        if not confirm("Cancel Booking", "Are you sure you want to cancel this booking?", danger=True):
            return
        try:
            self.app.booking_mgr.cancel_booking(bid)
        except ValueError as exc:
            messagebox.showerror("Booking error", str(exc))
            return
        self.refresh()

    def reschedule_selected(self):
        bid = self._selected_id()
        if bid is None:
            return
        booking = self.app.booking_mgr.get_booking(bid)
        if booking is None:
            return
        lock_reason = self.app.booking_mgr.reschedule_lock_reason(booking)
        if lock_reason:
            messagebox.showwarning("Can't reschedule", lock_reason)
            return
        win = tk.Toplevel(self)
        win.title("Reschedule Booking")
        win.configure(bg=theme.BG)
        win.resizable(False, False)

        tk.Label(win, text=booking["facility_name"], bg=theme.BG, fg=theme.TEXT,
                 font=(theme.FONT_FAMILY, 10, "bold")).pack(anchor="w", padx=16, pady=(16, 2))
        tk.Label(win, text=f"Currently: {booking['booking_date']}  {booking['start_time']} \u2013 {booking['end_time']}",
                 bg=theme.BG, fg=theme.MUTED_TEXT, font=(theme.FONT_FAMILY, 9)
                 ).pack(anchor="w", padx=16, pady=(0, 10))

        picker = DateTimeRangePicker(
            win, timeline_height=220,
            initial_date=date.fromisoformat(booking["booking_date"]),
            initial_start=booking["start_time"], initial_end=booking["end_time"])
        picker.pack(padx=16)

        def booked_ranges(target_date):
            ranges = [
                (b["start_time"], b["end_time"])
                for b in self.app.booking_mgr.list_bookings(None, None, None)
                if b["facility_id"] == booking["facility_id"] and b["booking_date"] == target_date
                and b["status"] in ("Pending", "Approved") and b["id"] != bid
            ]
            if target_date == date.today().isoformat():
                ranges.append(("00:00", datetime.now().strftime("%H:%M")))
            return ranges
        picker.set_booked_provider(booked_ranges)

        def do_reschedule():
            new_date, new_start, new_end = picker.get_selection()
            if not (new_start and new_end):
                messagebox.showwarning("Missing info", "Please pick a time slot on the timeline.")
                return
            try:
                self.app.booking_mgr.reschedule(bid, new_date, new_start, new_end)
            except ValueError as exc:
                messagebox.showerror("Booking error", str(exc))
                return
            self.toast("Booking rescheduled.")
            win.destroy()
            self.refresh()

        ttk.Button(win, text="Save", style="Primary.TButton",
                   command=do_reschedule).pack(pady=(10, 16))

