import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QRectF, QPointF, QTimer, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import (
    QPixmap, QPainter, QColor, QPen, QBrush, QFont, QLinearGradient,
    QPainterPath, QPolygonF, QShortcut, QKeySequence,
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QMessageBox, QFrame,
)
from ultralytics import YOLO

# ----------------------------------------------------------------------------
# Config (Updated to match the dark plum & soft lavender palette)
# ----------------------------------------------------------------------------
BASE_DIR = Path("E:/BioSort")
AUTO_ADVANCE = True  # jump to the next image shortly after "Confirm & Segregate"

C = {
    "bg": "#120A12", "panel": "#1F1321", "panel2": "#291A2B", "line": "#3D2540",
    "text": "#F5EEF8", "muted": "#A38FA6", "accent": "#C4B5FD", "accent2": "#A78BFA",
    "ok": "#34D399", "warn": "#FBBF24", "bad": "#F87171",
}

# Bin definitions with safety protocols & PPE requirements
BINS = {
    "white": {
        "title": "White · Sharps", "color": "#F1F5F9",
        "note": "Puncture-proof container. Do not recap or bend needles.",
        "ppe": "Required PPE: Heavy-duty utility gloves, puncture-resistant apron.",
        "short": "White",
    },
    "yellow": {
        "title": "Yellow · Soiled waste", "color": "#FACC15",
        "note": "Anatomical / soiled waste bin. Incineration required.",
        "ppe": "Required PPE: Nitrile gloves, safety goggles, lab coat / gown.",
        "short": "Yellow",
    },
    "blue": {
        "title": "Blue · Recyclable plastic", "color": "#38BDF8",
        "note": "Blue / white translucent bin for recyclable plastic and tubing.",
        "ppe": "Required PPE: Standard examination gloves.",
        "short": "Blue",
    },
    "green": {
        "title": "Green · General waste", "color": "#4ADE80",
        "note": "General, non-infectious municipal waste.",
        "ppe": "Required PPE: Standard handling standards.",
        "short": "Green",
    },
}


def rgba(hex_color, alpha):
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def eyebrow(text):
    lbl = QLabel(text.upper())
    f = QFont("Segoe UI")
    f.setPixelSize(11)
    f.setBold(True)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color: {C['muted']};")
    return lbl


# ----------------------------------------------------------------------------
# Custom painted widgets
# ----------------------------------------------------------------------------
class Logo(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(44, 44)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(C["accent"])))
        p.drawRoundedRect(QRectF(self.rect()), 12, 12)
        pen = QPen(QColor(C["bg"]), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(22, 12), QPointF(22, 32))
        p.drawLine(QPointF(12, 22), QPointF(32, 22))


class BinIcon(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(72, 88)
        self.color = QColor("#94A3B8")

    def set_color(self, hex_color):
        self.color = QColor(hex_color)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color.darker(125))
        p.drawRoundedRect(QRectF(26, 4, 20, 10), 4, 4)
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(4, 12, 64, 12), 5, 5)
        body = QPainterPath()
        body.moveTo(10, 27)
        body.lineTo(62, 27)
        body.lineTo(57, 78)
        body.quadTo(56, 84, 50, 84)
        body.lineTo(22, 84)
        body.quadTo(16, 84, 15, 78)
        body.closeSubpath()
        p.drawPath(body)
        pen = QPen(QColor(C["panel"]), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(36, 42), QPointF(36, 68))
        p.drawLine(QPointF(23, 55), QPointF(49, 55))


class ImageStage(QWidget):
    """Image viewer: dotted grid, rounded image, corner brackets, label chip, scan sweep."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 400)
        self._pix = None
        self._scaled = None
        self._scaled_key = None
        self._label = ""
        self._scan = 1.0
        self._placeholder = "No images found"
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(800)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_scan)

    def set_placeholder(self, text):
        self._placeholder = text
        self.update()

    def set_content(self, pix, label):
        self._pix = pix if (pix is not None and not pix.isNull()) else None
        self._label = label
        self._scaled = None
        self._scaled_key = None
        self.update()

    def start_scan(self):
        if self._pix is None:
            return
        self._anim.stop()
        self._anim.start()

    def _on_scan(self, v):
        self._scan = float(v)
        self.update()

    def _image_rect(self):
        avail = QRectF(self.rect()).adjusted(48, 56, -48, -40)
        sz = self._pix.size().scaled(avail.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(avail.center().x() - sz.width() / 2,
                      avail.center().y() - sz.height() / 2,
                      sz.width(), sz.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        bg = QPainterPath()
        bg.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.setClipPath(bg)
        p.fillPath(bg, QBrush(QColor("#0D070D")))
        p.setPen(QPen(QColor(196, 181, 253, 15), 1))
        step = 36
        for x in range(0, self.width(), step):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)

        if self._pix is None:
            p.setPen(QColor(C["muted"]))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self._placeholder)
            return

        r = self._image_rect()
        key = (int(r.width()), int(r.height()))
        if self._scaled is None or self._scaled_key != key:
            self._scaled = self._pix.scaled(
                key[0], key[1], Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._scaled_key = key

        clip = QPainterPath()
        clip.addRoundedRect(r, 12, 12)
        p.save()
        p.setClipPath(clip)
        p.drawPixmap(r.toRect(), self._scaled)

        if self._scan < 1.0:
            y = r.top() + self._scan * r.height()
            glow = QLinearGradient(0, y - 28, 0, y)
            glow.setColorAt(0, QColor(196, 181, 253, 0))
            glow.setColorAt(1, QColor(196, 181, 253, 70))
            p.fillRect(QRectF(r.left(), y - 28, r.width(), 28), QBrush(glow))
            line = QLinearGradient(r.left(), 0, r.right(), 0)
            line.setColorAt(0, QColor(196, 181, 253, 0))
            line.setColorAt(0.5, QColor(C["accent"]))
            line.setColorAt(1, QColor(196, 181, 253, 0))
            p.fillRect(QRectF(r.left(), y - 1, r.width(), 2), QBrush(line))
        p.restore()

        g, ln = 10, 26
        l, t, rt, b = r.left() - g, r.top() - g, r.right() + g, r.bottom() + g
        pen = QPen(QColor(C["accent"]), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        corners = [
            [(l, t + ln), (l, t), (l + ln, t)],
            [(rt - ln, t), (rt, t), (rt, t + ln)],
            [(l, b - ln), (l, b), (l + ln, b)],
            [(rt - ln, b), (rt, b), (rt, b - ln)],
        ]
        for pts in corners:
            p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))

        if self._label:
            f = QFont("Segoe UI")
            f.setPixelSize(13)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(self._label)
            chip = QRectF(l, max(8.0, t - 34), tw + 26, 28)
            path = QPainterPath()
            path.addRoundedRect(chip, 8, 8)
            p.fillPath(path, QBrush(QColor(C["accent"])))
            p.setPen(QColor(C["bg"]))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, self._label)


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class MedicalWasteSorterApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.base_dir = BASE_DIR
        self.model_path = self.base_dir / "Model" / "best.pt"
        self.images_dir = self.base_dir / "Images"

        try:
            self.model = YOLO(str(self.model_path))
        except Exception as e:
            QMessageBox.critical(self, "Model Error", f"Could not load model:\n{e}")
            sys.exit(1)

        self.image_files = []
        if self.images_dir.exists():
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.PNG"):
                self.image_files.extend(list(self.images_dir.glob(ext)))
        self.image_files = sorted(set(self.image_files))

        self.current_index = 0
        self.current_bin = None
        self.current_label = ""
        self.confirmed = set()
        self.counts = {k: 0 for k in BINS}
        self.total = 0
        self.recent = []

        self.advance_timer = QTimer(self)
        self.advance_timer.setSingleShot(True)
        self.advance_timer.timeout.connect(self.load_next_image)

        self.init_ui()
        self.apply_stylesheet()
        self.init_shortcuts()
        self.load_image_at_index()

    def init_ui(self):
        self.setWindowTitle("BioSort - Medical Waste Segregation Dashboard")
        self.resize(1360, 860)
        self.setMinimumSize(1120, 760)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(28, 22, 28, 24)
        main.setSpacing(16)

        main.addLayout(self.build_header())

        content = QHBoxLayout()
        content.setSpacing(20)
        content.addWidget(self.build_stage_card(), stretch=1)
        content.addWidget(self.build_side_panel())
        main.addLayout(content, stretch=1)

        main.addLayout(self.build_controls())

    def build_header(self):
        header = QHBoxLayout()
        header.setSpacing(14)
        header.addWidget(Logo())

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("BioSort AI")
        title.setObjectName("TitleLabel")
        sub = QLabel("Segregation station")
        sub.setObjectName("SubtitleLabel")
        titles.addWidget(title)
        titles.addWidget(sub)
        header.addLayout(titles)
        header.addStretch()

        self.model_chip = QLabel(f"Model &nbsp;<b>{self.model_path.name}</b>")
        self.model_chip.setObjectName("Chip")
        self.model_chip.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(self.model_chip)

        self.status_indicator = QLabel()
        self.status_indicator.setObjectName("Chip")
        self.status_indicator.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(self.status_indicator)
        self.set_status("System ready", C["ok"])
        return header

    def build_stage_card(self):
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        top = QHBoxLayout()
        tag = QLabel("ITEM SCAN")
        tag.setObjectName("Tag")
        self.file_label = QLabel("")
        self.file_label.setObjectName("Muted")
        self.speed_label = QLabel("")
        self.speed_label.setObjectName("Muted")
        top.addWidget(tag)
        top.addWidget(self.file_label)
        top.addStretch()
        top.addWidget(self.speed_label)
        lay.addLayout(top)

        self.stage = ImageStage()
        self.stage.set_placeholder(f"No images found in {self.images_dir}")
        lay.addWidget(self.stage, stretch=1)

        bottom = QHBoxLayout()
        legend = QLabel(" &nbsp;&nbsp; ".join(
            f'<span style="color:{b["color"]}">&#9632;</span> {b["short"]}'
            for b in BINS.values()))
        legend.setObjectName("Muted")
        legend.setTextFormat(Qt.TextFormat.RichText)
        self.counter_label = QLabel("")
        self.counter_label.setObjectName("Muted")
        self.counter_label.setTextFormat(Qt.TextFormat.RichText)
        bottom.addWidget(legend)
        bottom.addStretch()
        bottom.addWidget(self.counter_label)
        lay.addLayout(bottom)
        return card

    def build_side_panel(self):
        side = QWidget()
        side.setFixedWidth(450)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)
        lay.addWidget(self.build_safety_protocol_card())
        lay.addWidget(self.build_bin_card())
        lay.addWidget(self.build_session_card(), stretch=1)
        return side

    def build_safety_protocol_card(self):
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(8)
        
        lay.addWidget(eyebrow("Safety & Handling Protocol"))
        
        self.safety_ppe_label = QLabel("Scan an item to load safety instructions...")
        self.safety_ppe_label.setObjectName("SafetyText")
        self.safety_ppe_label.setWordWrap(True)
        lay.addWidget(self.safety_ppe_label)
        
        return card

    def build_bin_card(self):
        self.bin_card = QFrame()
        self.bin_card.setObjectName("BinCard")
        lay = QHBoxLayout(self.bin_card)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(20)

        self.bin_icon = BinIcon()
        lay.addWidget(self.bin_icon)

        col = QVBoxLayout()
        col.setSpacing(4)
        self.bin_title = eyebrow("Target disposal bin")
        self.bin_result_label = QLabel("Awaiting scan...")
        self.bin_result_label.setObjectName("BinTitle")
        self.bin_result_label.setWordWrap(True)
        self.bin_note_label = QLabel("")
        self.bin_note_label.setObjectName("Muted")
        self.bin_note_label.setWordWrap(True)
        col.addWidget(self.bin_title)
        col.addWidget(self.bin_result_label)
        col.addWidget(self.bin_note_label)
        lay.addLayout(col, stretch=1)
        self.update_bin_card_style(None)
        return self.bin_card

    def build_session_card(self):
        card = QFrame()
        card.setObjectName("Card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        lay.addWidget(eyebrow("Session"))

        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.stat_values = {}
        for key, caption, color in [("total", "Sorted", None)] + [
                (k, b["short"], b["color"]) for k, b in BINS.items()]:
            tile = QFrame()
            tile.setObjectName("Tile")
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(12, 10, 12, 10)
            tl.setSpacing(0)
            val = QLabel("0")
            val.setObjectName("StatValue")
            cap = QLabel(
                (f'<span style="color:{color}">&#9632;</span> ' if color else "") + caption)
            cap.setObjectName("Muted")
            cap.setTextFormat(Qt.TextFormat.RichText)
            tl.addWidget(val)
            tl.addWidget(cap)
            tiles.addWidget(tile)
            self.stat_values[key] = val
        lay.addLayout(tiles)

        lay.addSpacing(4)
        lay.addWidget(eyebrow("Recent"))
        self.recent_label = QLabel("")
        self.recent_label.setObjectName("RecentLog")
        self.recent_label.setTextFormat(Qt.TextFormat.RichText)
        self.recent_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.recent_label)
        lay.addStretch()
        self.refresh_session()
        return card

    def build_controls(self):
        controls = QHBoxLayout()
        controls.setSpacing(14)

        self.prev_btn = QPushButton("‹  Previous image")
        self.prev_btn.setObjectName("SecondaryButton")
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(self.load_prev_image)

        self.segregate_btn = QPushButton("Confirm segregate")
        self.segregate_btn.setObjectName("PrimaryButton")
        self.segregate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.segregate_btn.clicked.connect(self.trigger_segregation)

        self.next_btn = QPushButton("Next image")
        self.next_btn.setObjectName("SecondaryButton")
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(self.load_next_image)

        controls.addWidget(self.prev_btn, stretch=10)
        controls.addWidget(self.segregate_btn, stretch=17)
        controls.addWidget(self.next_btn, stretch=10)
        return controls

    def init_shortcuts(self):
        for key, slot in [
            ("Left", self.load_prev_image),
            ("Right", self.load_next_image),
            ("Return", self.trigger_segregation),
            ("Enter", self.trigger_segregation),
        ]:
            QShortcut(QKeySequence(key), self).activated.connect(slot)

    def apply_stylesheet(self):
        qss = f"""
            QMainWindow, QWidget#Root {{ background-color: {C['bg']}; }}
            QLabel {{ color: {C['text']}; font-family: 'Segoe UI', Arial, sans-serif; }}
            QLabel#TitleLabel {{ font-size: 22px; font-weight: 700; }}
            QLabel#SubtitleLabel {{ font-size: 13px; color: {C['muted']}; }}
            QLabel#Muted {{ font-size: 12px; color: {C['muted']}; }}
            QLabel#SafetyText {{ font-size: 13px; color: {C['text']}; font-weight: 600; }}
            QLabel#Chip {{
                font-size: 13px; font-weight: 600; color: {C['text']};
                background-color: {C['panel']}; border: 1px solid {C['line']};
                border-radius: 17px; padding: 8px 16px;
            }}
            QLabel#Tag {{
                font-size: 11px; font-weight: 700; color: {C['text']};
                background-color: {C['panel2']}; border: 1px solid {C['line']};
                border-radius: 7px; padding: 4px 10px;
            }}
            QFrame#Card {{
                background-color: {C['panel']}; border: 1px solid {C['line']};
                border-radius: 18px;
            }}
            QFrame#Tile {{
                background-color: {C['panel2']}; border: 1px solid {C['line']};
                border-radius: 12px;
            }}
            QLabel#StatValue {{ font-size: 22px; font-weight: 800; }}
            QLabel#BinTitle {{ font-size: 22px; font-weight: 800; }}
            QLabel#RecentLog {{ font-size: 13px; color: {C['text']}; }}
            QPushButton {{
                font-family: 'Segoe UI', Arial, sans-serif; font-size: 15px;
                font-weight: 600; border-radius: 16px; min-height: 58px;
            }}
            QPushButton#PrimaryButton {{
                color: #120A12; border: none; font-size: 16px; font-weight: 700;
                background-color: {C['accent']};
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: #DDD6FE;
            }}
            QPushButton#SecondaryButton {{
                background-color: {C['panel']}; color: {C['text']};
                border: 1px solid {C['line']};
            }}
            QPushButton#SecondaryButton:hover {{ background-color: {C['panel2']}; }}
        """
        self.setStyleSheet(qss)

    def set_status(self, text, color):
        self.status_indicator.setText(
            f'<span style="color:{C["text"]}">{text}</span>')
        self.status_indicator.setStyleSheet(
            f"border: 1px solid {C['line']}; background-color: {C['panel']};")

    def update_bin_card_style(self, bin_key):
        color = BINS[bin_key]["color"] if bin_key else C["line"]
        self.bin_card.setStyleSheet(
            f"QFrame#BinCard {{ background-color: {C['panel']};"
            f" border: 1px solid {C['line']}; border-radius: 18px; }}")
        self.bin_icon.set_color(color)

    def refresh_session(self):
        self.stat_values["total"].setText(str(self.total))
        for k, v in self.counts.items():
            self.stat_values[k].setText(str(v))
        if not self.recent:
            self.recent_label.setText(
                f'<span style="color:{C["muted"]}">No items sorted yet.</span>')
            return
        rows = []
        for label, key, fname in self.recent[:4]:
            rows.append(
                f'<div style="margin-bottom:8px">'
                f'<span style="color:{BINS[key]["color"]}">&#9632;</span>&nbsp; '
                f'<b>{label}</b> &nbsp;<span style="color:{C["muted"]}">'
                f'&rarr; {BINS[key]["short"]} &middot; {fname}</span></div>')
        self.recent_label.setText("".join(rows))

    @staticmethod
    def pretty(name):
        return name.replace("_", " ").title()

    def load_image_at_index(self):
        self.advance_timer.stop()

        if not self.image_files:
            self.stage.set_content(None, "")
            self.file_label.setText("")
            self.speed_label.setText("")
            self.counter_label.setText("")
            self.safety_ppe_label.setText("System idle.")
            self.bin_result_label.setText("System idle")
            self.bin_note_label.setText("")
            self.update_bin_card_style(None)
            self.set_status("No images found", C["bad"])
            return

        img_path = self.image_files[self.current_index]
        self.file_label.setText(img_path.name)
        self.counter_label.setText(
            f'Image <b style="color:{C["text"]}">{self.current_index + 1}</b> of '
            f'<b style="color:{C["text"]}">{len(self.image_files)}</b>')

        pixmap = QPixmap(str(img_path))
        self.stage.set_content(pixmap, "")
        self.set_status("Analyzing…", C["warn"])
        QApplication.processEvents()

        try:
            results = self.model(str(img_path), verbose=False)
        except Exception as e:
            self.set_status("Inference error", C["bad"])
            self.bin_result_label.setText("Inference failed")
            self.bin_note_label.setText(str(e))
            return

        detected_class_name = "Unknown"
        confidence_score = 0.0
        if results and results[0].probs is not None:
            probs = results[0].probs
            top1_index = int(probs.top1)
            confidence_score = float(probs.top1conf.item()) * 100
            detected_class_name = self.model.names[top1_index]

        bin_key, known = self.get_bin_mapping(detected_class_name.lower())
        info = BINS[bin_key]
        self.current_bin = bin_key
        self.current_label = self.pretty(detected_class_name)

        self.safety_ppe_label.setText(info["ppe"])

        self.bin_result_label.setText(info["title"])
        self.bin_note_label.setText(
            info["note"] if known else
            f"Unrecognised class '{detected_class_name}'. Handled as biohazard.")
        self.update_bin_card_style(bin_key)

        self.stage.set_content(pixmap, f"{detected_class_name.upper()} · {confidence_score:.2f}%")
        self.stage.start_scan()
        speed = getattr(results[0], "speed", None) or {}
        ms = speed.get("inference")
        self.speed_label.setText(f"Inference  {ms:.0f} ms" if ms is not None else "")

        if img_path in self.confirmed:
            self.set_status("Already sorted", C["accent2"])
        else:
            self.set_status("System ready", C["ok"])

    def load_next_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.load_image_at_index()

    def load_prev_image(self):
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self.load_image_at_index()

    def trigger_segregation(self):
        if not self.image_files or self.current_bin is None:
            return
        img_path = self.image_files[self.current_index]
        if img_path in self.confirmed:
            self.set_status("Already routed", C["warn"])
            return

        self.confirmed.add(img_path)
        self.counts[self.current_bin] += 1
        self.total += 1
        self.recent.insert(0, (self.current_label, self.current_bin, img_path.name))
        self.refresh_session()
        self.set_status(f"Routed to {BINS[self.current_bin]['short']} bin", C["ok"])

        if AUTO_ADVANCE and len(self.image_files) > 1:
            self.advance_timer.start(900)

    def get_bin_mapping(self, class_name):
        if any(k in class_name for k in ["needle", "syringe", "blade", "scalpel", "glass"]):
            return "white", True
        if any(k in class_name for k in ["cotton", "gauze", "soiled", "plaster", "blood"]):
            return "yellow", True
        if any(k in class_name for k in ["bottle", "tubing", "catheter", "syringe_plastic", "gloves"]):
            return "blue", True
        if any(k in class_name for k in ["paper", "cardboard", "box", "general"]):
            return "green", True
        return "yellow", False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MedicalWasteSorterApp()
    window.show()
    sys.exit(app.exec())
    