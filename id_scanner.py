"""
id_scanner.py
-------------
Webcam-based student ID card scanner. Opens a live camera preview, lets the
person line the card up in frame and capture a still, then tries to read the
Name, Student ID, Expiry Date and barcode number straight off the card so
they don't have to be typed in by hand. Detected fields are handed back to
the caller (still editable) rather than saved directly, since OCR on a
handheld card is never 100% reliable.

Two recognition passes run independently, so a missing dependency for one
doesn't block the other:
  1. pyzbar decodes the printed barcode directly -> barcode number. This is
     the most reliable field since it's just reading encoded bars, not
     guessing at printed text.
  2. pytesseract OCRs the card text -> Name / Student ID / Expiry Date,
     matched against the known card formats.

Optional dependencies (the dialog still opens and works for manual capture
without them - it just leaves the corresponding fields blank):
    pip install opencv-python pillow pyzbar pytesseract
plus the Tesseract OCR engine itself, which is a separate system install:
    - Windows: https://github.com/UB-Mannheim/tesseract/wiki
      (after installing, either add it to PATH or set
       pytesseract.pytesseract.tesseract_cmd = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe")
    - macOS:   brew install tesseract
    - Linux:   sudo apt install tesseract-ocr
pyzbar also needs the system zbar library (brew install zbar / apt install
libzbar0) in addition to the `pip install pyzbar` package.

Note: this module was already class-based (CameraScanDialog is the one
stateful piece here) before the rest of the app's OOP pass, so it's
unchanged other than living alongside the newly-converted modules.
"""

import re
import tkinter as tk
from tkinter import ttk

import theme

try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False

try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

try:
    import pytesseract
    HAVE_TESSERACT = True
except ImportError:
    HAVE_TESSERACT = False

try:
    from pyzbar.pyzbar import decode as _zbar_decode
    HAVE_PYZBAR = True
except ImportError:
    HAVE_PYZBAR = False


STUDENT_ID_PATTERN = re.compile(r"\b(\d{2}[A-Z]{3}\d{5})\b")
EXPIRY_PATTERN = re.compile(r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b")

_IGNORE_NAME_WORDS = ("STUDENT", "TARUMT", "TUNKU", "ABDUL", "RAHMAN", "UNIVERSITY",
                       "MANAGEMENT", "TECHNOLOGY", "EXPIRY", "DATE", "CARD")


def extract_text_fields(raw_text):
    """Best-effort parse of OCR'd card text into Name / Student ID / Expiry."""
    result = {"name": "", "student_id": "", "expiry_date": ""}
    upper_no_space = raw_text.upper().replace(" ", "")

    sid_match = STUDENT_ID_PATTERN.search(upper_no_space)
    if sid_match:
        result["student_id"] = sid_match.group(1)

    exp_match = EXPIRY_PATTERN.search(raw_text)
    if exp_match:
        result["expiry_date"] = exp_match.group(1).replace("/", "-")

    # Name heuristic: the first all-letters line of 2+ words that isn't one
    # of the card's fixed labels and doesn't itself contain the student ID.
    for line in raw_text.splitlines():
        clean = line.strip()
        if not clean or len(clean.split()) < 2:
            continue
        letters_only = re.sub(r"[^A-Za-z ]", "", clean).strip()
        if len(letters_only) < 4:
            continue
        if any(word in clean.upper() for word in _IGNORE_NAME_WORDS):
            continue
        if STUDENT_ID_PATTERN.search(clean.replace(" ", "").upper()):
            continue
        result["name"] = letters_only.title()
        break

    return result


def extract_barcode_number(cv2_frame):
    """Decode a printed barcode directly from a captured frame, if possible."""
    if not HAVE_PYZBAR:
        return ""
    try:
        results = _zbar_decode(cv2_frame)
    except Exception:
        return ""
    digit_values = [r.data.decode("utf-8", "ignore") for r in results]
    digit_values = [v for v in digit_values if v.isdigit()]
    return digit_values[0] if digit_values else ""


class CameraScanDialog(tk.Toplevel):
    """
    Modal dialog: live webcam preview -> Capture -> auto-read -> the caller's
    `on_result(fields)` callback receives whatever was detected (a dict with
    keys name / student_id / expiry_date / barcode_number, any of which may
    be an empty string if that field wasn't confidently detected).
    """

    PREVIEW_W, PREVIEW_H = 640, 400

    def __init__(self, master, on_result, camera_index=0):
        super().__init__(master)
        self.title("Scan Student ID Card")
        self.configure(bg=theme.BG)
        self.resizable(False, False)
        self.transient(master)
        self.on_result = on_result
        self.cap = None
        self._frame_bgr = None
        self._preview_job = None
        self._last_fields = {}

        if not (HAVE_CV2 and HAVE_PIL):
            ttk.Label(self, padding=24, wraplength=320,
                      text="Camera scanning needs OpenCV and Pillow:\n\n"
                           "pip install opencv-python pillow").pack()
            ttk.Button(self, text="Close", style="Neutral.TButton",
                       command=self.destroy).pack(pady=(0, 18))
            return

        self.video_label = tk.Label(self, bg="black",
                                     width=self.PREVIEW_W, height=self.PREVIEW_H)
        self.video_label.pack(padx=16, pady=(16, 8))

        ttk.Label(self, style="Muted.TLabel",
                  text="Line up the card inside the frame, then click Capture. "
                       "Detected fields fill in automatically.").pack()

        btns = ttk.Frame(self)
        btns.pack(pady=12)
        self.capture_btn = ttk.Button(btns, text="Capture", style="Primary.TButton",
                                       command=self._capture)
        self.capture_btn.pack(side="left", padx=6)
        self.retake_btn = ttk.Button(btns, text="Scan Again", style="Neutral.TButton",
                                      command=self._retake, state="disabled")
        self.retake_btn.pack(side="left", padx=6)
        self.done_btn = ttk.Button(btns, text="Done", style="Success.TButton",
                                    command=self.destroy, state="disabled")
        self.done_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Cancel", style="Ghost.TButton",
                   command=self.destroy).pack(side="left", padx=6)

        self.status_lbl = ttk.Label(self, style="Muted.TLabel", text="", wraplength=560)
        self.status_lbl.pack(pady=(0, 14))

        self.cap = cv2.VideoCapture(camera_index)
        if not self.cap.isOpened():
            self.status_lbl.configure(
                text=f"Could not open the webcam (camera index {camera_index}).")
            self.capture_btn.configure(state="disabled")
        else:
            self._update_preview()

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ---- live preview ----------------------------------------------------
    def _update_preview(self):
        ok, frame = self.cap.read()
        if ok:
            self._frame_bgr = frame
            self._show(frame)
        self._preview_job = self.after(30, self._update_preview)

    def _show(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb).resize((self.PREVIEW_W, self.PREVIEW_H))
        photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=photo)
        self.video_label.image = photo  # keep a reference alive

    # ---- capture + recognition --------------------------------------------
    def _capture(self):
        if self._frame_bgr is None:
            return
        if self._preview_job:
            self.after_cancel(self._preview_job)
            self._preview_job = None
        self._show(self._frame_bgr)
        self.capture_btn.configure(state="disabled")
        self.retake_btn.configure(state="normal")
        self.status_lbl.configure(text="Reading card...")
        self.after(50, self._run_recognition)

    def _retake(self):
        self.retake_btn.configure(state="disabled")
        self.done_btn.configure(state="disabled")
        self.capture_btn.configure(state="normal")
        self.status_lbl.configure(text="")
        self._update_preview()

    def _run_recognition(self):
        frame = self._frame_bgr
        fields = {"name": "", "student_id": "", "expiry_date": "", "barcode_number": ""}
        notes = []

        fields["barcode_number"] = extract_barcode_number(frame)
        if not HAVE_PYZBAR:
            notes.append("barcode reading needs: pip install pyzbar (+ system zbar library)")

        if HAVE_TESSERACT:
            try:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_CUBIC)
                gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                              cv2.THRESH_BINARY, 31, 11)
                raw_text = pytesseract.image_to_string(gray)
                for key, value in extract_text_fields(raw_text).items():
                    if value:
                        fields[key] = value
            except Exception as exc:
                notes.append(f"OCR text reading failed ({exc})")
        else:
            notes.append("text OCR needs: pip install pytesseract + the Tesseract engine")

        self._last_fields = fields

        # Apply immediately - no extra "use this scan" click needed. The
        # dialog stays open only so the person can Scan Again if something
        # came out wrong, or click Done when they're happy with the result.
        if self.on_result:
            self.on_result(fields)

        found = ", ".join(k.replace("_", " ") for k, v in fields.items() if v) or "nothing"
        message = f"Filled in: {found}."
        if notes:
            message += " (" + "; ".join(notes) + ")"
        if found == "nothing":
            message += " Try Scan Again with better lighting/focus, or fill in manually."
        self.status_lbl.configure(text=message)
        self.done_btn.configure(state="normal")

    def _release_camera(self):
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def destroy(self):
        if self._preview_job:
            try:
                self.after_cancel(self._preview_job)
            except Exception:
                pass
            self._preview_job = None
        self._release_camera()
        super().destroy()
