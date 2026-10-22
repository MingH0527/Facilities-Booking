"""
approve_decline_application.py
Facility Booking System - module 2: Approve / Decline Application
----------------------------------------------------------------
The admin decision step on a submitted booking application:

  Refuse / Pending Application   - Cancelled / Pending status changes
  Approve Generate Confirmation  - Approved / Completed status changes,
                                   confirmation prompt, database update

Supplied as a mixin so the decision behaviour stays exactly where it was in
the admin booking screen at runtime, while the code for it lives in its own
module. `BookingTab` in booking_facilities.py picks it up by inheritance;
`self.tree`, `self.app` and `self.refresh()` come from that class.
"""


from tkinter import messagebox

from widgets import confirm


class ApproveDeclineMixin:
    """Approve / refuse / pending decisions on a selected booking."""

    def change_status(self, new_status):
        bid = self._selected_id()
        if bid is None:
            return
        vals = self.tree.item(bid, "values")
        facility, requester = vals[1], vals[2]
        verb = {"Approved": "approve", "Completed": "mark as completed",
                "Cancelled": "cancel"}.get(new_status, "update")
        danger = new_status == "Cancelled"
        if not confirm(f"{new_status} Booking",
                       f"Are you sure you want to {verb} the booking for "
                       f"'{facility}' requested by {requester}?", danger=danger):
            return
        try:
            self.app.booking_mgr.update_status(bid, new_status)
        except ValueError as exc:
            messagebox.showerror("Booking error", str(exc))
            return
        self.refresh()
        self.app.refresh_dashboard()
