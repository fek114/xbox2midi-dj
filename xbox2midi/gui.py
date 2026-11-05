"""
Xbox2MIDI DJ - Grafik arayüz (PySide6 / Qt 6, karanlık tema — Adım 1: XDJ-AZ CFX & Stems Sürümü).

Thread modeli:
  * Qt ana thread  : arayüz, durum kontrolleri (1 Hz), log/görselleştirme (30 Hz)
  * Worker thread  : BridgeEngine._run (60 FPS) — GUI'yi asla bloklamaz
"""
from __future__ import annotations

import html
import math
import os
import sys
from typing import Callable, Dict, Optional

from PySide6.QtCore import (QEasingCurve, QPointF, QRectF, QSettings, Qt, QTimer,
                            QVariantAnimation)
from PySide6.QtGui import (QColor, QFont, QIcon, QKeySequence, QLinearGradient,
                           QPainter, QPainterPath, QPalette, QPen, QRadialGradient,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame,
                               QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QMainWindow, QPlainTextEdit,
                               QPushButton, QSizePolicy, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import config
from . import midi_out as mo
from .controller import GameControllerInput
from .engine import BridgeEngine, _pool

# --------------------------------------------------------------------------- #
#  Tasarım tokenları
# --------------------------------------------------------------------------- #
C_BG0 = "#07090E"
C_BG1 = "#0E1119"
C_TEXT = "#E8EBF4"
C_MUTED = "#8A93A8"
C_DIM = "#4B5368"
C_GREEN = "#1FE0A2"
C_CYAN = "#22C7FF"
C_VIOLET = "#8B6CFF"
C_RED = "#FF4D6D"
C_AMBER = "#FFB547"

XBOX_COLORS = {"A": "#3DDC84", "B": "#FF4D6D", "X": "#3FA9FF", "Y": "#FFC93D"}

LOG_COLORS = {"cc": "#7CC8FF", "on": C_GREEN, "off": "#7D869B", "info": "#C9CFDC",
              "ok": C_GREEN, "warn": C_AMBER, "err": C_RED}


def resource_path(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


STYLESHEET = f"""
* {{ color: {C_TEXT}; }}
QMainWindow, QWidget#root {{ background: {C_BG0}; }}
QFrame[card="true"] {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(255,255,255,0.055), stop:1 rgba(255,255,255,0.025));
    border: 1px solid rgba(255,255,255,0.075);
    border-radius: 16px;
}}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 23px; font-weight: 800; letter-spacing: 0.3px; }}
QLabel#subtitle {{ color: {C_MUTED}; font-size: 12px; }}
QLabel#cardTitle {{ color: {C_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.3px; }}
QLabel#cardValue {{ font-size: 15px; font-weight: 700; }}
QLabel#cardDetail {{ color: {C_MUTED}; font-size: 11px; }}
QLabel#sectionTitle {{ color: {C_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1.3px; }}
QLabel#pill {{
    border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 700;
    background: rgba(255,255,255,0.06); color: {C_MUTED};
}}
QLabel#pill[mode="live"] {{ background: rgba(31,224,162,0.14); color: {C_GREEN}; }}
QLabel#pill[mode="learn"] {{ background: rgba(255,181,71,0.20); color: {C_AMBER}; border: 1px solid {C_AMBER}; }}
QLabel#pill[mode="preview"] {{ background: rgba(255,181,71,0.12); color: {C_AMBER}; }}
QLabel#stat {{ color: {C_MUTED}; font-size: 12px; font-family: Menlo; }}

QPushButton#startBtn, QPushButton#stopBtn {{
    font-size: 16px; font-weight: 800; letter-spacing: 0.6px;
    border: none; border-radius: 14px; padding: 12px 10px; min-height: 24px;
}}
QPushButton#startBtn {{
    color: #03140F;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2BF0B0, stop:1 #14B8F0);
}}
QPushButton#startBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5CFFC8, stop:1 #3FCBFF);
}}
QPushButton#startBtn:pressed {{ background: #12A9D8; }}
QPushButton#stopBtn {{
    color: #FFFFFF;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF4D6D, stop:1 #FF7B47);
}}
QPushButton#stopBtn:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FF6B86, stop:1 #FF9466);
}}
QPushButton#stopBtn:pressed {{ background: #E23D5C; }}
QPushButton#startBtn:disabled, QPushButton#stopBtn:disabled {{
    background: rgba(255,255,255,0.045); color: {C_DIM};
}}

QPushButton#cfxSlotBtn {{
    background: rgba(255,255,255,0.045);
    border: 1.5px solid rgba(255,255,255,0.14);
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 800;
    color: {C_TEXT};
}}
QPushButton#cfxSlotBtn:hover {{
    border-color: rgba(34,199,255,0.6);
}}
QPushButton#cfxSlotBtn[state="on"] {{
    background: rgba(31,224,162,0.20);
    border: 1.8px solid {C_GREEN};
    color: {C_GREEN};
}}
QPushButton#cfxSlotBtn[state="selected_off"] {{
    background: rgba(139,108,255,0.14);
    border: 1.5px solid {C_VIOLET};
    color: {C_TEXT};
}}
QPushButton#learnToggle {{
    background: rgba(255,255,255,0.045);
    border: 1.5px solid rgba(255,255,255,0.12);
    border-radius: 10px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 800;
    color: {C_MUTED};
}}
QPushButton#learnToggle:hover {{
    border-color: rgba(255,181,71,0.55);
    color: {C_TEXT};
}}
QPushButton#learnToggle:checked {{
    background: rgba(255,181,71,0.18);
    border: 1.5px solid {C_AMBER};
    color: {C_AMBER};
}}

QPushButton#ghost {{
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 9px; padding: 5px 11px; font-size: 12px; color: {C_TEXT};
}}
QPushButton#ghost:hover {{ background: rgba(255,255,255,0.11); }}
QPushButton#ghost:disabled {{ color: {C_DIM}; }}

QComboBox {{
    background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 9px; padding: 5px 10px; font-size: 12px; min-width: 210px;
}}
QComboBox:hover {{ border-color: rgba(34,199,255,0.55); }}
QComboBox:disabled {{ color: {C_DIM}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: #141824; border: 1px solid rgba(255,255,255,0.1);
    selection-background-color: rgba(34,199,255,0.25); padding: 4px; outline: 0;
}}

QCheckBox {{ color: {C_MUTED}; font-size: 11px; spacing: 5px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.25); background: rgba(255,255,255,0.04);
}}
QCheckBox::indicator:checked {{ background: {C_CYAN}; border-color: {C_CYAN}; }}

QTabWidget::pane {{ border: none; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {C_MUTED}; padding: 7px 14px; margin-right: 4px;
    font-size: 12px; font-weight: 700; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {C_TEXT}; border-bottom: 2px solid {C_CYAN}; }}
QTabBar::tab:hover {{ color: {C_TEXT}; }}

QPlainTextEdit#log {{
    background: rgba(0,0,0,0.38); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; padding: 8px; font-family: Menlo; font-size: 12px;
    selection-background-color: rgba(34,199,255,0.3);
}}
QTableWidget {{
    background: rgba(0,0,0,0.30); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; gridline-color: rgba(255,255,255,0.05); font-size: 12px;
    alternate-background-color: rgba(255,255,255,0.02);
}}
QHeaderView::section {{
    background: transparent; color: {C_MUTED}; border: none; padding: 8px;
    font-size: 11px; font-weight: 700; letter-spacing: 1px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.14); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.24); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: #161B27; color: {C_TEXT}; border: 1px solid rgba(255,255,255,0.12);
            padding: 6px; border-radius: 6px; }}
"""


def card() -> QFrame:
    f = QFrame()
    f.setProperty("card", True)
    return f


def glow(widget: QWidget, color: str, radius: int = 32) -> QGraphicsDropShadowEffect:
    eff = QGraphicsDropShadowEffect(widget)
    c = QColor(color)
    c.setAlpha(140)
    eff.setColor(c)
    eff.setBlurRadius(radius)
    eff.setOffset(0, 5)
    widget.setGraphicsEffect(eff)
    return eff


# --------------------------------------------------------------------------- #
#  Özel widget'lar
# --------------------------------------------------------------------------- #
class StatusLed(QWidget):
    """Nabız atan durum LED'i."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self._color = QColor(C_RED)
        self._phase = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1800)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)
        self._anim.valueChanged.connect(self._tick)
        self._anim.start()

    def _tick(self, v) -> None:
        self._phase = float(v)
        self.update()

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        pulse = 0.5 - 0.5 * math.cos(self._phase * 2 * math.pi)
        halo = QRadialGradient(c, 12)
        hc = QColor(self._color)
        hc.setAlpha(int(40 + 90 * pulse))
        halo.setColorAt(0.0, hc)
        hc2 = QColor(self._color)
        hc2.setAlpha(0)
        halo.setColorAt(1.0, hc2)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(c, 12, 12)
        core = QRadialGradient(c + QPointF(-1.5, -1.5), 6)
        core.setColorAt(0, self._color.lighter(150))
        core.setColorAt(1, self._color)
        p.setBrush(core)
        p.drawEllipse(c, 5.5, 5.5)


class DualCfxStickPad(QWidget):
    """
    Sol Analog Çubuk için özel 'XDJ-AZ Çift Deck CFX Topuzu' görselleştiricisi:
      * Sol Yarım Ay (Deck 1 · B00A): Sol Aşağı=%0 (64) ➔ 90° Sol=%50 (96) ➔ Sol Yukarı=%100 (127)
      * Sağ Yarım Ay (Deck 2 · B00C): Sağ Aşağı=%0 (64) ➔ 90° Sağ=%50 (96) ➔ Sağ Yukarı=%100 (127)
    """

    def __init__(self, title: str = "SOL ANALOG · ÇİFT DECK CFX KNOB",
                 kx: str = "LX", ky: str = "LY", m1: str = "LX", m2: str = "RX_CFX",
                 hex1: str = "B00A", hex2: str = "B00C", click_key: str = "L3",
                 tag: str = "CFX", rest: int = config.STICK_CENTER, parent=None) -> None:
        super().__init__(parent)
        self.title, self.kx, self.ky, self.m1, self.m2 = title, kx, ky, m1, m2
        self.hex1, self.hex2, self.click_key, self.tag, self.rest = hex1, hex2, click_key, tag, rest
        self.x = 0.0
        self.y = 0.0
        self.d1_cc = rest
        self.d2_cc = rest
        self.d1_pct = 0
        self.d2_pct = 0
        self.active_deck = 0
        self.hold_locked = False
        self.pressed = False
        self.active = False
        self.setMinimumSize(210, 206)
        self.setFixedHeight(206)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, axes: Dict, midi: Dict, buttons: Dict,
                  d1_pct: int, d2_pct: int, active_deck: int,
                  hold_locked: bool, active: bool) -> None:
        self.x = axes.get(self.kx, 0.0)
        self.y = axes.get(self.ky, 0.0)
        self.d1_cc = midi.get(self.m1, self.rest)
        self.d2_cc = midi.get(self.m2, self.rest)
        self.d1_pct = d1_pct
        self.d2_pct = d2_pct
        self.active_deck = active_deck
        self.hold_locked = hold_locked
        self.pressed = buttons.get(self.click_key, False)
        self.active = active
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        f_top = QFont("Menlo")
        f_top.setPixelSize(11)
        f_top.setBold(True)
        p.setFont(f_top)
        p.setPen(QColor(C_CYAN))
        p.drawText(QRectF(0, 0, w, 15), Qt.AlignCenter, self.title)

        r = min(w - 50, h - 74) / 2 - 2
        c = QPointF(w / 2, 17 + r)

        bg = QRadialGradient(c, r)
        bg.setColorAt(0, QColor(28, 34, 50))
        bg.setColorAt(1, QColor(12, 15, 23))
        ring = QColor(C_AMBER) if self.hold_locked else (
            QColor(C_GREEN) if self.active_deck in (1, 2) else QColor(255, 255, 255, 42)
        )
        p.setPen(QPen(ring, 2.2 if self.active_deck in (1, 2) or self.hold_locked else 1.2))
        p.setBrush(bg)
        p.drawEllipse(c, r, r)

        # Sol ve Sağ Deck ayırıcı dikey koridor (|LX| <= 0.20)
        dz_w = r * config.CFX_SIDE_DEADZONE
        p.setPen(QPen(QColor(255, 255, 255, 35), 1, Qt.DotLine))
        p.drawLine(QPointF(c.x() - dz_w, c.y() - r + 4), QPointF(c.x() - dz_w, c.y() + r - 4))
        p.drawLine(QPointF(c.x() + dz_w, c.y() - r + 4), QPointF(c.x() + dz_w, c.y() + r - 4))

        # 90° Orta (%50) yatay kılavuz çizgisi
        p.setPen(QPen(QColor(34, 199, 255, 65), 1.2, Qt.DashLine))
        p.drawLine(QPointF(c.x() - r + 4, c.y()), QPointF(c.x() + r - 4, c.y()))

        # Çember kenarında %0, %50, %100 etiketleri (Sol = Deck 1, Sağ = Deck 2)
        f_lbl = QFont("Menlo")
        f_lbl.setPixelSize(9)
        f_lbl.setBold(True)
        p.setFont(f_lbl)

        # Sol kenar etiketleri (Deck 1)
        p.setPen(QColor(C_GREEN) if self.active_deck == 1 else QColor(C_CYAN))
        p.drawText(QRectF(2, c.y() - r - 2, 36, 13), Qt.AlignLeft | Qt.AlignVCenter, "%100")
        p.drawText(QRectF(2, c.y() - 7, 36, 13), Qt.AlignLeft | Qt.AlignVCenter, "D1 %50")
        p.drawText(QRectF(2, c.y() + r - 11, 36, 13), Qt.AlignLeft | Qt.AlignVCenter, "%0")

        # Sağ kenar etiketleri (Deck 2)
        p.setPen(QColor(C_GREEN) if self.active_deck == 2 else QColor(C_VIOLET))
        p.drawText(QRectF(w - 38, c.y() - r - 2, 36, 13), Qt.AlignRight | Qt.AlignVCenter, "%100")
        p.drawText(QRectF(w - 38, c.y() - 7, 36, 13), Qt.AlignRight | Qt.AlignVCenter, "%50 D2")
        p.drawText(QRectF(w - 38, c.y() + r - 11, 36, 13), Qt.AlignRight | Qt.AlignVCenter, "%0")

        # Canlı Nokta Konumu
        reach = r - 9
        pos = QPointF(c.x() + self.x * reach, c.y() - self.y * reach)
        accent = (
            QColor(C_AMBER) if self.hold_locked
            else (QColor(C_GREEN) if self.active_deck == 1
                  else (QColor(C_CYAN) if self.active_deck == 2 else QColor(C_VIOLET)))
        )

        if self.active_deck in (1, 2):
            lc = QColor(accent)
            lc.setAlpha(170)
            p.setPen(QPen(lc, 2.4))
            p.drawLine(c, pos)

        halo = QRadialGradient(pos, 18)
        hc = QColor(accent)
        hc.setAlpha(115)
        halo.setColorAt(0, hc)
        hc.setAlpha(0)
        halo.setColorAt(1, hc)
        p.setPen(Qt.NoPen)
        p.setBrush(halo)
        p.drawEllipse(pos, 18, 18)
        p.setBrush(accent)
        p.drawEllipse(pos, 7, 7)

        # Alt Satır 1: Deck 1 CFX (Sol Yarı · B00A)
        f_sub = QFont("Menlo")
        f_sub.setPixelSize(10)
        f_sub.setBold(True)
        p.setFont(f_sub)
        p.setPen(QColor(C_GREEN) if self.active_deck == 1 else QColor(C_MUTED))
        p.drawText(
            QRectF(0, h - 55, w, 14),
            Qt.AlignCenter,
            f"SOL (Deck 1 · {self.hex1}): %{self.d1_pct:3d}  [MIDI {self.d1_cc:3d}]",
        )

        # Alt Satır 2: Deck 2 CFX (Sağ Yarı · B00C)
        p.setPen(QColor(C_CYAN) if self.active_deck == 2 else QColor(C_MUTED))
        p.drawText(
            QRectF(0, h - 40, w, 14),
            Qt.AlignCenter,
            f"SAĞ (Deck 2 · {self.hex2}): %{self.d2_pct:3d}  [MIDI {self.d2_cc:3d}]",
        )

        # Alt Satır 3: L3 Tık -> CFX Hold / Kilitle
        pill_r = QRectF(w / 2 - 96, h - 24, 192, 19)
        p.setBrush(QColor(255, 181, 71, 55) if self.hold_locked else QColor(20, 24, 34))
        p.setPen(QPen(QColor(C_AMBER) if self.hold_locked else QColor(255, 255, 255, 38), 1))
        p.drawRoundedRect(pill_r, 6, 6)
        f_clk = QFont("Menlo")
        f_clk.setPixelSize(10)
        f_clk.setBold(True)
        p.setFont(f_clk)
        p.setPen(QColor(C_AMBER) if self.hold_locked else QColor(C_TEXT))
        p.drawText(
            pill_r,
            Qt.AlignCenter,
            (f"🔒 {self.click_key}: {self.tag} KİLİTLİ (Çöz: {self.click_key})" if self.hold_locked
             else f"{self.click_key} Tık: {self.tag} Yüzdesini Kilitle"),
        )


class StickPad(QWidget):
    """Sağ Analog Çubuk Görselleştiricisi (Adım 2/3'te FX için kullanılacak)."""

    def __init__(self, label: str, kx: str, ky: str, click_key: str,
                 role_x: str, role_y: str, click_role: str, parent=None) -> None:
        super().__init__(parent)
        self.label = label
        self.kx = kx
        self.ky = ky
        self.click_key = click_key
        self.role_x = role_x
        self.role_y = role_y
        self.click_role = click_role
        self.x = 0.0
        self.y = 0.0
        self.mx = config.STICK_CENTER
        self.my = config.STICK_CENTER
        self.pressed = False
        self.active = False
        self.setMinimumSize(195, 206)
        self.setFixedHeight(206)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, axes: Dict, midi: Dict, buttons: Dict, active: bool) -> None:
        self.x = axes.get("RX", 0.0)
        self.y = axes.get("RY", 0.0)
        self.mx = midi.get("LY", config.STICK_CENTER)
        self.my = midi.get("RY", config.STICK_CENTER)
        self.pressed = buttons.get(self.click_key, False)
        self.active = active
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cbtn = config.BUTTON_BY_KEY[self.click_key]

        f_top = QFont("Menlo")
        f_top.setPixelSize(11)
        f_top.setBold(True)
        p.setFont(f_top)
        p.setPen(QColor(C_MUTED))
        p.drawText(QRectF(0, 0, w, 15), Qt.AlignCenter,
                   "SAĞ ANALOG · FX KONTROLÜ (ADIM 2)")

        r = min(w, h - 74) / 2 - 3
        c = QPointF(w / 2, 17 + r)

        bg = QRadialGradient(c, r)
        bg.setColorAt(0, QColor(28, 34, 50))
        bg.setColorAt(1, QColor(12, 15, 23))
        ring = QColor(C_GREEN) if self.pressed else QColor(255, 255, 255, 38)
        p.setPen(QPen(ring, 2.4 if self.pressed else 1.2))
        p.setBrush(bg)
        p.drawEllipse(c, r, r)

        p.setPen(QPen(QColor(34, 199, 255, 55), 1.3, Qt.DashLine))
        p.drawLine(QPointF(c.x() - r + 4, c.y()), QPointF(c.x() + r - 4, c.y()))
        p.setPen(QPen(QColor(139, 108, 255, 55), 1.3, Qt.DashLine))
        p.drawLine(QPointF(c.x(), c.y() - r + 4), QPointF(c.x(), c.y() + r - 4))

        reach = r - 10
        pos = QPointF(c.x() + self.x * reach, c.y() - self.y * reach)
        centered = (self.mx == config.STICK_CENTER and self.my == config.STICK_CENTER)
        accent = QColor(C_DIM) if not self.active else (QColor(C_VIOLET) if centered else QColor(C_CYAN))

        if not centered:
            lc = QColor(accent)
            lc.setAlpha(160)
            p.setPen(QPen(lc, 2.4))
            p.drawLine(c, pos)
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawEllipse(pos, 7, 7)

        f_sub = QFont("Menlo")
        f_sub.setPixelSize(10)
        f_sub.setBold(True)
        p.setFont(f_sub)
        p.setPen(QColor(C_MUTED))
        p.drawText(QRectF(0, h - 55, w, 14), Qt.AlignCenter, f"Sağ X: {self.mx:3d}")
        p.drawText(QRectF(0, h - 40, w, 14), Qt.AlignCenter, f"Sağ Y: {self.my:3d}")

        pill_r = QRectF(w / 2 - 90, h - 24, 180, 19)
        p.setBrush(QColor(31, 224, 162, 55) if self.pressed else QColor(20, 24, 34))
        p.setPen(QPen(QColor(C_GREEN) if self.pressed else QColor(255, 255, 255, 38), 1))
        p.drawRoundedRect(pill_r, 6, 6)
        f_clk = QFont("Menlo")
        f_clk.setPixelSize(10)
        f_clk.setBold(True)
        p.setFont(f_clk)
        p.setPen(QColor(C_GREEN) if self.pressed else QColor(C_TEXT))
        p.drawText(pill_r, Qt.AlignCenter, f"{self.click_key} Tık: {cbtn.hex_code} ({self.click_role})")


class TriggerBar(QWidget):
    """LT ve RT tetik çubuğu."""

    def __init__(self, key: str, short_role: str, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.short_role = short_role
        self.axis = config.AXIS_BY_KEY[key]
        self.value = 0
        self.active = False
        self.setFixedWidth(80)
        self.setFixedHeight(206)

    def set_state(self, midi: Dict, active: bool) -> None:
        self.value = midi.get(self.key, 0)
        self.active = active
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        f = QFont()
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(C_TEXT))
        p.drawText(QRectF(0, 0, w, 14), Qt.AlignCenter, f"{self.key} Tetik")

        mono = QFont("Menlo")
        mono.setPixelSize(11)
        mono.setBold(True)
        p.setFont(mono)
        p.setPen(QColor(C_CYAN))
        p.drawText(QRectF(0, 14, w, 14), Qt.AlignCenter, self.axis.hex_code)

        track = QRectF(w / 2 - 11, 31, 22, h - 72)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1.3))
        p.setBrush(QColor(12, 15, 22))
        p.drawRoundedRect(track, 11, 11)

        frac = self.value / 127.0
        if frac > 0:
            fh = max(18.0, track.height() * frac)
            fill = QRectF(track.left(), track.bottom() - fh, track.width(), fh)
            g = QLinearGradient(fill.bottomLeft(), track.topLeft())
            g.setColorAt(0, QColor(C_VIOLET))
            g.setColorAt(1, QColor(C_CYAN))
            path = QPainterPath()
            path.addRoundedRect(fill, 11, 11)
            p.fillPath(path, g)

        mono.setPixelSize(10)
        mono.setBold(False)
        p.setFont(mono)
        p.setPen(QColor(C_MUTED))
        p.drawText(QRectF(0, h - 34, w, 14), Qt.AlignCenter, self.short_role)
        mono.setBold(True)
        p.setFont(mono)
        p.setPen(QColor(C_CYAN) if self.value else QColor(C_MUTED))
        p.drawText(QRectF(0, h - 18, w, 15), Qt.AlignCenter, f"Değer: {self.value:3d}")


class ButtonPanel(QWidget):
    """
    LB = DUB ECHO (Bas-Aç/Bas-Kapat), RB = NOISE (Bas-Aç/Bas-Kapat),
    D-Pad (Stems), View/Menu ve ABXY (Pad FX) canlı görünümü.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.buttons: Dict[str, bool] = {}
        self.stems_muted: Dict[str, bool] = {}
        self.fx1_active: bool = False
        self.cfx_active: bool = False
        self.cfx_slot: str = "DUB_ECHO"
        self.banner: Optional[tuple] = None
        self.learn_mode: bool = False
        self.active = False
        self.setMinimumWidth(420)
        self.setFixedHeight(206)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_state(self, buttons: Dict, stems_muted: Dict, active: bool,
                  fx1_active: bool = False, cfx_active: bool = False,
                  cfx_slot: str = "DUB_ECHO", banner: Optional[tuple] = None,
                  learn_mode: bool = False) -> None:
        self.buttons = buttons
        self.stems_muted = stems_muted or {}
        self.active = active
        self.fx1_active = fx1_active
        self.cfx_active = cfx_active
        self.cfx_slot = cfx_slot
        self.banner = banner
        self.learn_mode = learn_mode
        self.update()

    def _on(self, key: str) -> bool:
        return bool(self.buttons.get(key))

    def _abxy_button(self, p: QPainter, c: QPointF, r: float, key: str,
                     hex_code: str, sub: str, color: str, tag_offset: QPointF) -> None:
        on = self._on(key)
        col = QColor(color)
        if on:
            halo = QRadialGradient(c, r * 2.1)
            hc = QColor(col)
            hc.setAlpha(150)
            halo.setColorAt(0, hc)
            hc.setAlpha(0)
            halo.setColorAt(1, hc)
            p.setPen(Qt.NoPen)
            p.setBrush(halo)
            p.drawEllipse(c, r * 2.1, r * 2.1)
            p.setBrush(col)
            p.setPen(QPen(col.lighter(140), 1.5))
        else:
            p.setBrush(QColor(20, 24, 34))
            dim = QColor(col)
            dim.setAlpha(140)
            p.setPen(QPen(dim, 1.5))
        p.drawEllipse(c, r, r)
        f = QFont()
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#07090E") if on else col)
        p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), Qt.AlignCenter, key)

        tag_r = QRectF(c.x() + tag_offset.x(), c.y() + tag_offset.y(), 68, 17)
        p.setBrush(QColor(20, 24, 36, 220))
        p.setPen(QPen(col if on else QColor(255, 255, 255, 35), 1))
        p.drawRoundedRect(tag_r, 4, 4)
        mf = QFont("Menlo")
        mf.setPixelSize(9)
        mf.setBold(True)
        p.setFont(mf)
        p.setPen(col if on else QColor(C_TEXT))
        p.drawText(tag_r, Qt.AlignCenter, f"{hex_code}·{sub}")

    def _pill_two_line(self, p: QPainter, rect: QRectF, key: str,
                       top_text: str, bottom_text: str, latched: bool = False,
                       selected_slot: bool = False) -> None:
        on = self._on(key)
        if on:
            g = QLinearGradient(rect.topLeft(), rect.topRight())
            g.setColorAt(0, QColor(C_VIOLET))
            g.setColorAt(1, QColor(C_CYAN))
            p.setBrush(g)
            p.setPen(Qt.NoPen)
        elif latched:
            p.setBrush(QColor(31, 224, 162, 55))
            p.setPen(QPen(QColor(C_GREEN), 1.8))
        elif selected_slot:
            p.setBrush(QColor(139, 108, 255, 35))
            p.setPen(QPen(QColor(C_VIOLET), 1.4))
        else:
            p.setBrush(QColor(20, 24, 34))
            p.setPen(QPen(QColor(255, 255, 255, 45), 1.2))
        p.drawRoundedRect(rect, 8, 8)

        f1 = QFont("Menlo")
        f1.setPixelSize(11)
        f1.setBold(True)
        p.setFont(f1)
        p.setPen(QColor("#07090E") if on else (QColor(C_GREEN) if latched else QColor(C_CYAN)))
        p.drawText(QRectF(rect.left(), rect.top() + 2, rect.width(), 15),
                   Qt.AlignCenter, top_text)

        f2 = QFont()
        f2.setPixelSize(9)
        f2.setBold(latched)
        p.setFont(f2)
        p.setPen(QColor("#07090E") if on else (QColor(C_GREEN) if latched else QColor(C_MUTED)))
        p.drawText(QRectF(rect.left(), rect.top() + 16, rect.width(), 13),
                   Qt.AlignCenter, bottom_text)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx = w / 2

        dub_on = self.cfx_active and self.cfx_slot == "DUB_ECHO"
        noise_on = self.cfx_active and self.cfx_slot == "NOISE"

        # 1) Üst sıra: LB (DUB ECHO) | View (9049) | Menu (9047 Beat FX) | RB (NOISE)
        top = 4
        self._pill_two_line(
            p,
            QRectF(cx - 206, top, 104, 33),
            "LB",
            "LB · DUB ECHO",
            "● AÇIK (ON)" if dub_on else ("Hazır (Kapalı)" if self.cfx_slot == "DUB_ECHO" else "Bas-Aç / Kapat"),
            latched=dub_on,
            selected_slot=(self.cfx_slot == "DUB_ECHO"),
        )
        self._pill_two_line(
            p,
            QRectF(cx - 96, top, 92, 33),
            "VIEW",
            "⧉ View · 9049",
            "Stem Mute/Solo",
        )
        self._pill_two_line(
            p,
            QRectF(cx + 4, top, 92, 33),
            "MENU",
            "≡ Menu · 9047",
            "BEAT FX: AÇIK" if self.fx1_active else "BEAT FX: KAPALI",
            latched=self.fx1_active,
        )
        self._pill_two_line(
            p,
            QRectF(cx + 102, top, 104, 33),
            "RB",
            "RB · NOISE",
            "● AÇIK (ON)" if noise_on else ("Hazır (Kapalı)" if self.cfx_slot == "NOISE" else "Bas-Aç / Kapat"),
            latched=noise_on,
            selected_slot=(self.cfx_slot == "NOISE"),
        )

        # 2) Sol Alt: D-Pad (Stems)
        dc = QPointF(cx - 115, top + 102)
        bw, bh = 54, 27
        for key, dx, dy, title, hex_code in (
            ("UP", 0, -1, "↑ VOCAL", "9042"),
            ("DOWN", 0, 1, "↓ DRUMS", "9043"),
            ("LEFT", -1, 0, "← INST", "9044"),
            ("RIGHT", 1, 0, "→ RESET", "9045"),
        ):
            r = QRectF(dc.x() + dx * 56 - bw / 2, dc.y() + dy * 30 - bh / 2, bw, bh)
            on = self._on(key)
            muted = bool(self.stems_muted.get(key, False))
            if on:
                p.setBrush(QColor(C_CYAN))
                p.setPen(QPen(QColor(C_CYAN), 1.2))
            elif muted:
                p.setBrush(QColor(255, 77, 109, 65))
                p.setPen(QPen(QColor(C_RED), 1.2))
            else:
                p.setBrush(QColor(20, 24, 34))
                p.setPen(QPen(QColor(255, 255, 255, 42), 1))
            p.drawRoundedRect(r, 5, 5)

            f1 = QFont("Menlo")
            f1.setPixelSize(9)
            f1.setBold(True)
            p.setFont(f1)
            p.setPen(QColor("#07090E") if on else (QColor(C_RED) if muted else QColor(C_TEXT)))
            p.drawText(QRectF(r.left(), r.top() + 2, r.width(), 12), Qt.AlignCenter, title)

            f2 = QFont("Menlo")
            f2.setPixelSize(9)
            p.setFont(f2)
            p.setPen(QColor("#07090E") if on else QColor(C_CYAN))
            p.drawText(QRectF(r.left(), r.top() + 13, r.width(), 12), Qt.AlignCenter, hex_code)

        # 3) Sağ Alt: ABXY (PadFX 1..4)
        fc = QPointF(cx + 95, top + 102)
        d = 26
        rad = 13
        self._abxy_button(p, QPointF(fc.x(), fc.y() - d), rad,
                          "Y", "903F", "Pad4", XBOX_COLORS["Y"], QPointF(-34, -33))
        self._abxy_button(p, QPointF(fc.x() - d, fc.y()), rad,
                          "X", "903E", "Pad3", XBOX_COLORS["X"], QPointF(-84, -8))
        self._abxy_button(p, QPointF(fc.x() + d, fc.y()), rad,
                          "B", "903D", "Pad2", XBOX_COLORS["B"], QPointF(16, -8))
        self._abxy_button(p, QPointF(fc.x(), fc.y() + d), rad,
                          "A", "903C", "Pad1", XBOX_COLORS["A"], QPointF(-34, 16))

        # 4) En alt durum çubuğu
        banner_r = QRectF(4, h - 25, w - 8, 20)
        mono = QFont("Menlo")
        mono.setPixelSize(10)
        mono.setBold(True)
        p.setFont(mono)

        if self.banner is not None:
            b_txt, b_kind = self.banner
            col = QColor(C_AMBER if b_kind == "warn" else C_GREEN)
            bg_c = QColor(col)
            bg_c.setAlpha(38)
            p.setBrush(bg_c)
            p.setPen(QPen(col, 1.2))
            p.drawRoundedRect(banner_r, 6, 6)
            p.setPen(col)
            p.drawText(banner_r, Qt.AlignCenter, b_txt)
            return

        if self.learn_mode:
            p.setBrush(QColor(255, 181, 71, 30))
            p.setPen(QPen(QColor(C_AMBER), 1))
            p.drawRoundedRect(banner_r, 6, 6)
            p.setPen(QColor(C_AMBER))
            txt = "🎯 LEARN MODU AKTİF (Eksenler Kilitli) → Aşağıdaki Sözlükten Bir Karta Tıklayın!"
        else:
            p.setPen(QColor(C_MUTED))
            txt = "Sol Analog Sol Yarı = Deck 1 CFX · Sağ Yarı = Deck 2 CFX · LB = Dub Echo · RB = Noise"
        p.drawText(banner_r, Qt.AlignCenter, txt)


class SniperChipButton(QPushButton):
    """
    'REKORDBOX MIDI IN HIZLI SÖZLÜK' içerisindeki tıklanabilir interaktif kart.
    """

    def __init__(self, hex_code: str, xbox_name: str, rb_func: str,
                 on_trigger: Callable[[str], bool], highlight: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.hex_code = hex_code
        self.xbox_name = xbox_name
        self.rb_func = rb_func
        self._on_trigger = on_trigger
        self._highlight = highlight
        self._sent_active = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(
            f"🎯 Tıkla & Gönder: {hex_code} ({xbox_name})\n"
            f"Rekordbox Fonksiyonu: {rb_func}\n"
            "Rekordbox'ta LEARN açıkken buraya tıklarsanız sadece bu kontrolün MIDI kodu gönderilir."
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(1)
        self._lbl = QLabel(self)
        self._lbl.setTextFormat(Qt.RichText)
        self._lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(self._lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._reset_visual)

        self._refresh_style()
        self.clicked.connect(self._handle_click)

    def _refresh_style(self) -> None:
        is_axis = self.hex_code.startswith("B0")
        badge_col = C_GREEN if self._highlight else (C_AMBER if is_axis else C_CYAN)
        border_col = "rgba(31,224,162,0.45)" if self._highlight else "rgba(255,255,255,0.085)"
        bg_col = "rgba(31,224,162,0.07)" if self._highlight else "rgba(255,255,255,0.038)"
        if self._sent_active:
            self.setStyleSheet(
                f"QPushButton {{ background: rgba(31,224,162,0.22); "
                f"border: 1.5px solid {C_GREEN}; border-radius: 8px; text-align: left; }}"
            )
            self._lbl.setText(
                f'<span style="font-family:Menlo; font-size:11px; font-weight:800; color:{C_GREEN};">'
                f'{self.hex_code} · ✓ Gönderildi!</span><br>'
                f'<span style="font-size:10px; font-weight:700; color:{C_TEXT};">'
                f'{html.escape(self.rb_func)}</span>'
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: {bg_col}; "
                f"border: 1px solid {border_col}; border-radius: 8px; text-align: left; }} "
                f"QPushButton:hover {{ background: rgba(34,199,255,0.14); border: 1px solid {badge_col}; }}"
            )
            self._lbl.setText(
                f'<span style="font-family:Menlo; font-size:11px; font-weight:800; color:{badge_col};">'
                f'🎯 {self.hex_code}</span> '
                f'<span style="font-size:11px; font-weight:700; color:{C_TEXT};">'
                f'= {html.escape(self.xbox_name)}</span><br>'
                f'<span style="font-size:10px; color:{C_MUTED};">{html.escape(self.rb_func)}</span>'
            )

    def _handle_click(self) -> None:
        ok = self._on_trigger(self.hex_code)
        if ok:
            self._sent_active = True
            self._refresh_style()
            self._timer.start(1100)

    def _reset_visual(self) -> None:
        self._sent_active = False
        self._refresh_style()


# --------------------------------------------------------------------------- #
#  Ana pencere
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} — XDJ-AZ CFX (Dub Echo & Noise) + Stems")
        self.setMinimumSize(1120, 920)
        self.settings = QSettings("Xbox2MIDI", "XboxDJ")

        self.midi = mo.MidiOut()
        try:
            self.gamepad: Optional[GameControllerInput] = GameControllerInput()
            gp_error = None
        except Exception as exc:
            self.gamepad = None
            gp_error = str(exc)
        self.engine = BridgeEngine(self.midi, self.gamepad)

        self._build_ui()
        self._populate_ports(initial=True)

        if gp_error:
            self.engine.emit(gp_error, "err")
        else:
            self.engine.emit(
                "Hazır · Sol Analog (Sol Yarı=Deck 1 CFX, Sağ Yarı=Deck 2 CFX) · LB=Dub Echo · RB=Noise.",
                "ok",
            )

        # Başlangıçta Rekordbox MIDI CSV dosyasını otomatik senkronize et
        self._install_rekordbox_csv(silent=True)

        self.ui_timer = QTimer(self, interval=33, timerType=Qt.PreciseTimer)
        self.ui_timer.timeout.connect(self._ui_tick)
        self.ui_timer.start()
        self.status_timer = QTimer(self, interval=1000)
        self.status_timer.timeout.connect(self._status_tick)
        self.status_timer.start()
        QTimer.singleShot(250, self._status_tick)
        self._sync_buttons()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(9)

        # 1) Başlık Barı
        header = QHBoxLayout()
        header.setSpacing(12)
        logo = QLabel()
        icon_path = resource_path("assets", "icon.png")
        if os.path.exists(icon_path):
            logo.setPixmap(QIcon(icon_path).pixmap(44, 44))
        header.addWidget(logo)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        t = QLabel(f"{config.APP_NAME} · XDJ-AZ CFX & Stems", objectName="title")
        st = QLabel(
            "Adım 1: Sol Analog Çift-Deck CFX Knob (%0➔%50➔%100) · LB = Dub Echo (Bas-Aç/Kapat) · RB = Noise (Bas-Aç/Kapat)",
            objectName="subtitle",
        )
        titles.addWidget(t)
        titles.addWidget(st)
        header.addLayout(titles)
        header.addStretch(1)
        self.csv_btn = QPushButton("📥 Rekordbox CSV Güncelle", objectName="ghost")
        self.csv_btn.setToolTip("Rekordbox MidiMappings klasörüne XDJ-AZ CFX & Stems .midi.csv eşlemesini yazar")
        self.csv_btn.clicked.connect(lambda: self._install_rekordbox_csv(silent=False))
        header.addWidget(self.csv_btn, alignment=Qt.AlignVCenter)
        self.stat_label = QLabel("0.0 Hz · 0 mesaj", objectName="stat")
        self.stat_label.setMinimumWidth(145)
        self.stat_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.stat_label, alignment=Qt.AlignVCenter)
        ver = QLabel(f"v{config.APP_VERSION}", objectName="pill")
        header.addWidget(ver, alignment=Qt.AlignVCenter)
        outer.addLayout(header)

        # 2) Durum Kartları
        cards = QHBoxLayout()
        cards.setSpacing(12)

        c1 = card()
        l1 = QHBoxLayout(c1)
        l1.setContentsMargins(14, 10, 14, 10)
        l1.setSpacing(10)
        self.led_pad = StatusLed()
        l1.addWidget(self.led_pad, alignment=Qt.AlignTop)
        v1 = QVBoxLayout()
        v1.setSpacing(2)
        v1.addWidget(QLabel("XBOX KUMANDASI", objectName="cardTitle"))
        self.pad_value = QLabel("Kumanda Bekleniyor", objectName="cardValue")
        self.pad_detail = QLabel("Bluetooth veya USB-C ile bağlayın", objectName="cardDetail")
        v1.addWidget(self.pad_value)
        v1.addWidget(self.pad_detail)
        l1.addLayout(v1, 1)
        cards.addWidget(c1, 1)

        c2 = card()
        l2 = QHBoxLayout(c2)
        l2.setContentsMargins(14, 10, 14, 10)
        l2.setSpacing(10)
        self.led_midi = StatusLed()
        l2.addWidget(self.led_midi, alignment=Qt.AlignTop)
        v2 = QVBoxLayout()
        v2.setSpacing(2)
        v2.addWidget(QLabel("MIDI ÇIKIŞ PORTU (KANAL 1 · SABİT)", objectName="cardTitle"))
        self.midi_value = QLabel("Port Kapalı", objectName="cardValue")
        v2.addWidget(self.midi_value)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.port_combo = QComboBox()
        self.port_combo.setToolTip("Rekordbox'ın dinleyeceği CoreMIDI çıkışı")
        self.port_combo.currentIndexChanged.connect(self._on_port_changed)
        self.refresh_btn = QPushButton("↻ Yenile", objectName="ghost")
        self.refresh_btn.setToolTip("MIDI hedeflerini yeniden tara")
        self.refresh_btn.clicked.connect(lambda: self._populate_ports())
        row.addWidget(self.port_combo, 1)
        row.addWidget(self.refresh_btn)
        v2.addLayout(row)
        l2.addLayout(v2, 1)
        cards.addWidget(c2, 1)
        outer.addLayout(cards)

        # 3) Başlat / Durdur
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(10)
        self.start_btn = QPushButton("▶  KÖPRÜYÜ BAŞLAT", objectName="startBtn")
        self.stop_btn = QPushButton("⏹  DURDUR", objectName="stopBtn")
        for b in (self.start_btn, self.stop_btn):
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.start_btn.setToolTip("Kısayol: ⌘↩")
        self.stop_btn.setToolTip("Kısayol: ⌘.")
        self.start_btn.clicked.connect(self.start_bridge)
        self.stop_btn.clicked.connect(self.stop_bridge)
        ctrl_row.addWidget(self.start_btn, 3)
        ctrl_row.addWidget(self.stop_btn, 2)
        self.start_glow = glow(self.start_btn, C_GREEN)
        self.stop_glow = glow(self.stop_btn, C_RED)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self.start_bridge)
        QShortcut(QKeySequence("Ctrl+."), self, activated=self.stop_bridge)
        outer.addLayout(ctrl_row)

        # 4) XDJ-AZ CFX Kontrol & Rekordbox Senkron Barı
        cfx_bar = card()
        rl = QHBoxLayout(cfx_bar)
        rl.setContentsMargins(12, 7, 12, 7)
        rl.setSpacing(8)

        self.btn_dub_echo = QPushButton("🟣 LB (L1) = DUB ECHO: KAPALI", objectName="cfxSlotBtn")
        self.btn_dub_echo.setCursor(Qt.PointingHandCursor)
        self.btn_dub_echo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_dub_echo.setToolTip(
            "XDJ-AZ DUB ECHO Butonu (LB / Sol Tampon):\n"
            "• Basıldığında Rekordbox'ta Dub Echo'yu seçer (904A x3) ve CFX On (9048) açar/kapatır.\n"
            "• Buraya fareyle tıklayarak da test edebilirsiniz."
        )
        self.btn_dub_echo.clicked.connect(lambda: self.engine.trigger_cfx_button("DUB_ECHO"))
        rl.addWidget(self.btn_dub_echo, 2)

        self.btn_noise = QPushButton("🔵 RB (R1) = NOISE: KAPALI", objectName="cfxSlotBtn")
        self.btn_noise.setCursor(Qt.PointingHandCursor)
        self.btn_noise.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_noise.setToolTip(
            "XDJ-AZ NOISE Butonu (RB / Sağ Tampon):\n"
            "• Basıldığında Rekordbox'ta Noise'u seçer (904B x3) ve CFX On (9048) açar/kapatır.\n"
            "• Buraya fareyle tıklayarak da test edebilirsiniz."
        )
        self.btn_noise.clicked.connect(lambda: self.engine.trigger_cfx_button("NOISE"))
        rl.addWidget(self.btn_noise, 2)

        self.btn_fx = QPushButton("🟢 MENU = BEAT FX: KAPALI", objectName="cfxSlotBtn")
        self.btn_fx.setCursor(Qt.PointingHandCursor)
        self.btn_fx.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_fx.setToolTip(
            "Menu (≡) Tuşu = Beat FX On/Off (Bas-Aç / Bas-Kapat):\n"
            "• Rekordbox'ta o an seçili olan Beat FX'i açar/kapatır (9047 FX1 + 904D FX2).\n"
            "• Efekt seviyesini Sağ Analog ile verirsiniz (Sol yarı = Deck 1, Sağ yarı = Deck 2)."
        )
        self.btn_fx.clicked.connect(self.engine.trigger_fx_button)
        rl.addWidget(self.btn_fx, 2)

        self.btn_sync_dub = QPushButton("🔄 Dub Echo'ya Eşitle", objectName="ghost")
        self.btn_sync_dub.setCursor(Qt.PointingHandCursor)
        self.btn_sync_dub.setToolTip("Rekordbox'ta CFX 'DUB ECHO' seçiliyken tıklarsanız uygulamayı senkronize eder")
        self.btn_sync_dub.clicked.connect(lambda: self.engine.sync_cfx_state("DUB_ECHO", False))
        rl.addWidget(self.btn_sync_dub)

        self.btn_sync_noise = QPushButton("🔄 Noise'a Eşitle", objectName="ghost")
        self.btn_sync_noise.setCursor(Qt.PointingHandCursor)
        self.btn_sync_noise.setToolTip("Rekordbox'ta CFX 'NOISE' seçiliyken tıklarsanız uygulamayı senkronize eder")
        self.btn_sync_noise.clicked.connect(lambda: self.engine.sync_cfx_state("NOISE", False))
        rl.addWidget(self.btn_sync_noise)

        self.btn_learn_mode = QPushButton(
            "🎯 MIDI Learn Modu: KAPALI",
            objectName="learnToggle",
        )
        self.btn_learn_mode.setCheckable(True)
        self.btn_learn_mode.setChecked(False)
        self.btn_learn_mode.setCursor(Qt.PointingHandCursor)
        self.btn_learn_mode.setToolTip(
            "Sniper MIDI Learn Modu:\n"
            "Bu şalter açıkken fiziksel kumandadan gelen analog eksen gürültüsü susturulur.\n"
            "Aşağıdaki Hızlı Sözlük'ten istediğiniz kutucuğa tıklayarak Rekordbox'a %100 hatasız öğretin!"
        )
        self.btn_learn_mode.toggled.connect(self._on_learn_mode_toggled)
        rl.addWidget(self.btn_learn_mode)

        outer.addWidget(cfx_bar)

        # 5) Canlı Kumanda & Çift Deck CFX Knob Paneli
        live = card()
        live.setMinimumHeight(248)
        lv = QVBoxLayout(live)
        lv.setContentsMargins(14, 10, 14, 10)
        lv.setSpacing(4)
        lh = QHBoxLayout()
        lh.addWidget(QLabel(
            "CANLI XBOX KUMANDASI · SOL ANALOG = DECK 1 & DECK 2 CFX KNOB · LB = DUB ECHO · RB = NOISE",
            objectName="sectionTitle",
        ))
        lh.addStretch(1)
        self.mode_pill = QLabel("BEKLEMEDE", objectName="pill")
        lh.addWidget(self.mode_pill)
        lv.addLayout(lh)
        vis = QHBoxLayout()
        vis.setSpacing(10)
        self.lt_bar = TriggerBar("LT", "Sol Tetik")
        self.rt_bar = TriggerBar("RT", "Sağ Tetik")
        self.left_pad = DualCfxStickPad()
        self.right_pad = DualCfxStickPad("SAĞ ANALOG · ÇİFT DECK BEAT FX", "RX", "RY", "LY", "RY",
                                         "B00B", "B00D", "R3", "FX", 0)
        self.btn_panel = ButtonPanel()
        vis.addWidget(self.lt_bar)
        vis.addWidget(self.left_pad, 2)
        vis.addWidget(self.btn_panel, 3)
        vis.addWidget(self.right_pad, 2)
        vis.addWidget(self.rt_bar)
        lv.addLayout(vis)
        outer.addWidget(live)

        # 6) İnteraktif "Rekordbox MIDI IN Hızlı Sözlük" (Tıkla & Gönder Sniper MIDI Learn)
        outer.addWidget(self._build_quick_dictionary_card())

        # 7) Sekmeler: Log + Eşleme Matrisi + Rehber
        tabs_card = card()
        tv = QVBoxLayout(tabs_card)
        tv.setContentsMargins(14, 4, 14, 10)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        log_page = QWidget()
        lp = QVBoxLayout(log_page)
        lp.setContentsMargins(0, 6, 0, 0)
        lp.setSpacing(5)
        bar = QHBoxLayout()
        self.chk_analog = QCheckBox("Analog (CC / B0xx) mesajlarını göster")
        self.chk_analog.setChecked(True)
        self.chk_analog.toggled.connect(lambda v: setattr(self.engine, "log_analog", v))
        bar.addWidget(self.chk_analog)
        bar.addStretch(1)
        clear = QPushButton("Temizle", objectName="ghost")
        clear.clicked.connect(lambda: self.log_view.clear())
        bar.addWidget(clear)
        lp.addLayout(bar)
        self.log_view = QPlainTextEdit(objectName="log")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(600)
        self.log_view.setUndoRedoEnabled(False)
        self.log_view.setMinimumHeight(115)
        lp.addWidget(self.log_view)
        self.tabs.addTab(log_page, "Canlı Sinyal Monitörü")
        self.tabs.addTab(self._build_matrix(), "Detaylı MIDI IN Sözlüğü ve Eşleme Matrisi")
        self.tabs.addTab(self._build_help(), "Adım 1: XDJ-AZ CFX (Noise & Dub Echo) Kurulum Rehberi")
        tv.addWidget(self.tabs)
        outer.addWidget(tabs_card, 1)

    def _build_quick_dictionary_card(self) -> QFrame:
        box = card()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel(
            "🔍 REKORDBOX 'MIDI IN' HIZLI SÖZLÜK & SNIPER MIDI LEARN (Yeşil Kartlar = Adım 1 CFX)",
            objectName="sectionTitle",
        ))
        hdr.addStretch(1)
        hint = QLabel("Rekordbox'ta LEARN açıp istediğiniz karta tıklayın → %100 izole MIDI sinyali gönderilir",
                      objectName="cardDetail")
        hdr.addWidget(hint)
        lay.addLayout(hdr)

        items = [
            # --- 1. Sıra: Adım 1 CFX (Sol Analog Deck 1/2 + LB Dub Echo + RB Noise) ---
            ("B00A", "Sol Analog (Sol Yarı)", "CFX ParameterCH1 (Deck 1 Knob)", True),
            ("B00C", "Sol Analog (Sağ Yarı)", "CFX ParameterCH2 (Deck 2 Knob)", True),
            ("9048", "CFX On Şalteri (LB/RB)", "CFX On (Efekt Aç/Kapat)", True),
            ("904A", "CFX Select Next (Aşağı ↓)", "CFX Select Next (LB Dub Echo)", True),
            ("904B", "CFX Select Back (Yukarı ↑)", "CFX Select Back (RB Noise)", True),
            # --- 2. Sıra: D-Pad Stems + View ---
            ("9042", "D-Pad Yukarı ↑", "ActiveStem Vocal (Deck 1)", False),
            ("9043", "D-Pad Aşağı ↓", "ActiveStem Drums (Deck 1)", False),
            ("9044", "D-Pad Sol ←", "ActiveStem Inst (Deck 1)", False),
            ("9045", "D-Pad Sağ →", "Stems Reset (Orijinal)", False),
            ("9049", "View (⧉) Tuşu", "ActiveStem Mute/Solo", False),
            # --- 3. Sıra: ABXY PadFX + R3 ---
            ("903C", "A Tuşu", "PadFX1 Pad1 (1/4 Roll)", False),
            ("903D", "B Tuşu", "PadFX1 Pad2 (1/2 Roll)", False),
            ("903E", "X Tuşu", "PadFX1 Pad3 (Reverb)", False),
            ("903F", "Y Tuşu", "PadFX1 Pad4 (Spiral)", False),
            ("B00B", "Sağ Analog (Sol Yarı)", "FX1-1 LevelDepth (Deck 1 FX)", True),
            ("B00D", "Sağ Analog (Sağ Yarı)", "FX2-1 LevelDepth (Deck 2 FX)", True),
            ("9047", "Menu (≡) Tuşu", "FX1-1 On (Beat FX Aç/Kapat)", True),
            ("904D", "Menu (≡) ile birlikte", "FX2-1 On (Beat FX 2 Aç/Kapat)", True),
        ]

        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(5)
        cols = 5
        for idx, (hex_code, xbox_name, rb_func, hi) in enumerate(items):
            r, c = divmod(idx, cols)
            btn = SniperChipButton(hex_code, xbox_name, rb_func, self.engine.send_learn_signal, highlight=hi)
            grid.addWidget(btn, r, c)

        lay.addLayout(grid)
        return box

    def _build_matrix(self) -> QWidget:
        rows = [
            (
                b.hex_code,
                b.label,
                f"Note {b.note} (Buton · 0x90)",
                b.rekordbox_cmd,
                b.function,
            )
            for b in config.BUTTONS
        ] + [
            (
                a.hex_code,
                a.label,
                f"CC {a.cc} ({'Deck 1/2 CFX %0-%100' if 'cfx' in a.kind else '0–127'})",
                a.rekordbox_cmd,
                a.function,
            )
            for a in config.AXES
        ]
        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels([
            "REKORDBOX MIDI IN",
            "XBOX TUŞU / EKSENİ",
            "MIDI TÜRÜ & NUMARASI",
            "REKORDBOX FONKSİYONU",
            "GÖREVİ & AÇIKLAMA",
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.NoFocus)
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if c == 0:
                    it.setForeground(QColor(C_AMBER if v.startswith("B0") else C_CYAN))
                    f = QFont("Menlo")
                    f.setPixelSize(13)
                    f.setBold(True)
                    it.setFont(f)
                elif c == 1:
                    f = QFont()
                    f.setPixelSize(12)
                    f.setBold(True)
                    it.setFont(f)
                elif c == 3:
                    it.setForeground(QColor(C_GREEN))
                    f = QFont("Menlo")
                    f.setPixelSize(11)
                    it.setFont(f)
                table.setItem(r, c, it)
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(table)
        return w

    def _build_help(self) -> QWidget:
        text = QPlainTextEdit(objectName="log")
        text.setReadOnly(True)
        text.setPlainText(
            "🎛 ADIM 1: XDJ-AZ TARZI SOUND COLOR FX (CFX) KURULUM & KULLANIM REHBERİ\n"
            "══════════════════════════════════════════════════════════════════════════\n"
            "1) SOL ANALOG ÇUBUK (ÇİFT DECK CFX KNOB — Seçenek 1):\n"
            "   • Kolu SOLA yatırdığınızda DECK 1 CFX (B00A / CFX ParameterCH1) kontrol edilir:\n"
            "       - Sol Aşağı (Saat 7 yönü)  = %0 Efekt (MIDI 64 — Saat 12 Nötr)\n"
            "       - Sol Orta (90° Sol)       = %50 Efekt (MIDI 96 — Saat 2.5 yönü)\n"
            "       - Sol Yukarı (Saat 11 yönü)= %100 Full Efekt (MIDI 127 — Saat 5 tam açık)\n"
            "   • Kolu 90° SAĞA yatırdığınızda aynı hareketin simetriğiyle DECK 2 CFX (B00C / CFX ParameterCH2)\n"
            "     kontrol edilir.\n"
            "   • Analoğu tek başına hareket ettirmek CFX'i açıp kapatmaz; sadece topuzu çevirir!\n"
            "   • İpucu: L3'e (Sol Analoğun içine) tıklarsanız CFX yüzdesini o anki konumda kilitleyebilirsiniz.\n\n"
            "2) LB = DUB ECHO & RB = NOISE (BAS-AÇ / BAS-KAPAT):\n"
            "   • Rekordbox CFX Menü Sırası: FILTER -> JET -> CRUSH -> NOISE (4) -> PITCH -> SPACE -> DUB ECHO (7)\n"
            "   • LB (Sol Tampon) tuşuna bastığınızda 3 adım aşağı (904A x3) inip Dub Echo'yu AÇAR, tekrar basınca KAPATIR.\n"
            "   • RB (Sağ Tampon) tuşuna bastığınızda 3 adım yukarı (904B x3) çıkıp Noise'u AÇAR, tekrar basınca KAPATIR.\n"
            "   • Eğer menü kayarsa üstteki '🔄 Dub Echo'ya Eşitle' veya '🔄 Noise'a Eşitle' butonlarıyla anında eşitleyebilirsiniz.\n\n"
            "3) REKORDBOX 'FX' SEKMESİ KONTROL LİSTESİ (ÇOK ÖNEMLİ!):\n"
            "   Rekordbox MIDI penceresinde 'FX' sekmesinde şu 5 satırın 'Deck' sütunu mutlaka '-' (tire) olmalıdır:\n"
            "   • CFX ParameterCH1  | Deck: - | MIDI IN: B00A | Type: Knob/Slider\n"
            "   • CFX ParameterCH2  | Deck: - | MIDI IN: B00C | Type: Knob/Slider\n"
            "   • CFX On            | Deck: - | MIDI IN: 9048 | Type: Button\n"
            "   • CFX Select Next   | Deck: - | MIDI IN: 904A | Type: Button\n"
            "   • CFX Select Back   | Deck: - | MIDI IN: 904B | Type: Button\n"
            "   (Üstteki yeşil sözlük kartlarına tıklayarak veya CSV import ederek 5 saniyede eşleyebilirsiniz)."
        )
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.addWidget(text)
        return w

    # ------------------------------------------------------------------ #
    def _on_learn_mode_toggled(self, checked: bool) -> None:
        self.engine.learn_mode = checked
        self.btn_learn_mode.setText(
            f"🎯 MIDI Learn Modu: {'AÇIK (Kilitli)' if checked else 'KAPALI'}"
        )
        if checked:
            self.engine.set_banner(
                "🎯 LEARN MODU AKTİF: Fiziksel kumanda susturuldu — Yeşil CFX kartlarına tıklayın!",
                "warn",
                4.0,
            )
            self.engine.emit(
                "🎯 [MIDI Learn Modu AÇIK] Fiziksel eksen gürültüsü kilitlendi. Sözlük kartlarına tıklayarak Rekordbox'a öğretin.",
                "warn",
            )
        else:
            self.engine.set_banner("Canlı kumanda dinlemesi tekrar aktif.", "ok", 1.8)
            self.engine.emit("🎯 [MIDI Learn Modu KAPALI] Fiziksel kumanda akışı normale döndü.", "ok")
        self._sync_buttons()

    def _update_cfx_bar_visuals(self, cfx_slot: str, cfx_active: bool) -> None:
        dub_on = cfx_active and cfx_slot == "DUB_ECHO"
        noise_on = cfx_active and cfx_slot == "NOISE"

        if dub_on:
            self.btn_dub_echo.setText("🟣 LB (L1) = DUB ECHO: ● AÇIK (ON)")
            self.btn_dub_echo.setProperty("state", "on")
        elif cfx_slot == "DUB_ECHO":
            self.btn_dub_echo.setText("🟣 LB (L1) = DUB ECHO: HAZIR (KAPALI)")
            self.btn_dub_echo.setProperty("state", "selected_off")
        else:
            self.btn_dub_echo.setText("🟣 LB (L1) = DUB ECHO: KAPALI")
            self.btn_dub_echo.setProperty("state", "off")

        if noise_on:
            self.btn_noise.setText("🔵 RB (R1) = NOISE: ● AÇIK (ON)")
            self.btn_noise.setProperty("state", "on")
        elif cfx_slot == "NOISE":
            self.btn_noise.setText("🔵 RB (R1) = NOISE: HAZIR (KAPALI)")
            self.btn_noise.setProperty("state", "selected_off")
        else:
            self.btn_noise.setText("🔵 RB (R1) = NOISE: KAPALI")
            self.btn_noise.setProperty("state", "off")

        for b in (self.btn_dub_echo, self.btn_noise):
            b.style().unpolish(b)
            b.style().polish(b)

        fx_on = self.engine.fx1_active
        self.btn_fx.setText("🟢 MENU = BEAT FX: ● AÇIK (ON)" if fx_on else "🟢 MENU = BEAT FX: KAPALI")
        self.btn_fx.setProperty("state", "on" if fx_on else "off")
        self.btn_fx.style().unpolish(self.btn_fx)
        self.btn_fx.style().polish(self.btn_fx)

    # ------------------------------------------------------------------ #
    #  Rekordbox CSV Otomatik Kurulumu
    # ------------------------------------------------------------------ #
    def _install_rekordbox_csv(self, silent: bool = False) -> None:
        rb_dir = os.path.expanduser(
            "~/Library/Application Support/Pioneer/rekordbox6/MidiMappings"
        )
        proj_csv = resource_path("Xbox_DJ_Port.midi.csv")
        try:
            with open(proj_csv, "wb") as f:
                f.write(config.build_rekordbox_csv(config.VIRTUAL_PORT_NAME).encode("utf-8"))
            if os.path.isdir(rb_dir):
                for dev_name in (config.VIRTUAL_PORT_NAME, "IAC Sürücüsü Yol 1"):
                    target = os.path.join(rb_dir, f"{dev_name}.midi.csv")
                    with open(target, "wb") as f:
                        f.write(config.build_rekordbox_csv(dev_name).encode("utf-8"))
            if not silent:
                self.engine.emit(
                    "Rekordbox 'XDJ-AZ CFX & Stems' MIDI eşleme dosyaları (.midi.csv) güncellendi (Deck: '-' düzeltmeli).",
                    "ok",
                )
        except Exception as exc:
            if not silent:
                self.engine.emit(f"CSV yazma hatası: {exc}", "err")

    # ------------------------------------------------------------------ #
    #  MIDI port yönetimi
    # ------------------------------------------------------------------ #
    def _populate_ports(self, initial: bool = False) -> None:
        wanted = self.settings.value("port_uid", mo.VIRTUAL_TARGET_ID, int) if initial \
            else self.port_combo.currentData()
        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItem(f"⚡ {config.VIRTUAL_PORT_NAME} — Sanal (önerilen)", mo.VIRTUAL_TARGET_ID)
        try:
            dests = mo.list_destinations()
        except Exception as exc:
            dests = []
            self.engine.emit(f"MIDI hedefleri listelenemedi: {exc}", "err")
        for d in dests:
            self.port_combo.addItem(("🎛 " if d.is_iac else "◦ ") + d.name, d.unique_id)
        idx = self.port_combo.findData(wanted)
        self.port_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.port_combo.blockSignals(False)
        if not initial and not dests:
            self.engine.emit("Harici/IAC MIDI hedefi bulunamadı — sanal port kullanılabilir.", "info")
        iac = [d.name for d in dests if d.is_iac]
        if initial and iac:
            self.engine.emit(f"IAC sürücüsü algılandı: {', '.join(iac)}", "info")
        if initial or self.port_combo.currentData() != wanted or not self.midi.is_open:
            self._on_port_changed()

    def _on_port_changed(self, *_args) -> None:
        uid = self.port_combo.currentData()
        if uid is None:
            return
        try:
            if uid == mo.VIRTUAL_TARGET_ID:
                label = self.midi.open_virtual()
            else:
                label = self.midi.open_destination(int(uid))
            self.settings.setValue("port_uid", int(uid))
            self.engine.emit(f"MIDI çıkışı açıldı: {label}", "ok")
        except Exception as exc:
            self.engine.emit(f"MIDI portu açılamadı: {exc}", "err")
        self._status_tick()

    # ------------------------------------------------------------------ #
    #  Köprü kontrolü
    # ------------------------------------------------------------------ #
    def start_bridge(self) -> None:
        if self.engine.running:
            return
        if self.engine.start():
            if self.gamepad and not self.gamepad.info().connected:
                self.engine.emit("Köprü hazır — kumanda bağlandığı anda sinyal akışı başlayacak.", "warn")
        self._sync_buttons()

    def stop_bridge(self) -> None:
        if not self.engine.running:
            return
        self.engine.stop()
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        running = self.engine.running
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.port_combo.setEnabled(not running)
        self.refresh_btn.setEnabled(not running)
        self.start_glow.setEnabled(not running)
        self.stop_glow.setEnabled(running)
        self.start_btn.setText("●  KÖPRÜ ÇALIŞIYOR" if running else "▶  KÖPRÜYÜ BAŞLAT")
        if self.engine.learn_mode:
            mode = "learn"
            self.mode_pill.setText("🎯 LEARN MODU · EKSENLER KİLİTLİ")
        elif running:
            mode = "live"
            self.mode_pill.setText("CANLI · XDJ-AZ CFX AKTİF")
        else:
            mode = "preview" if self.gamepad else ""
            self.mode_pill.setText("ÖNİZLEME · SÖZLÜK TIKLA-GÖNDER HAZIR")
        self.mode_pill.setProperty("mode", mode)
        self.mode_pill.style().unpolish(self.mode_pill)
        self.mode_pill.style().polish(self.mode_pill)

    # ------------------------------------------------------------------ #
    #  Zamanlayıcılar
    # ------------------------------------------------------------------ #
    def _status_tick(self) -> None:
        if self.gamepad is not None:
            info = self.gamepad.info()
        else:
            info = None
        if info and info.connected:
            self.led_pad.set_color(C_GREEN)
            self.pad_value.setText(f"Bağlı — {info.name}")
            parts = []
            if info.category:
                parts.append(info.category)
            if info.battery is not None and info.battery > 0:
                parts.append(f"Pil %{round(info.battery * 100)}" + (" ⚡" if info.charging else ""))
            parts.append("Arka plan dinleme açık")
            self.pad_detail.setText(" · ".join(parts))
        else:
            self.led_pad.set_color(C_RED)
            self.pad_value.setText("Kumanda Bekleniyor")
            self.pad_detail.setText("Bluetooth veya USB-C ile bağlayın" if self.gamepad
                                    else "GameController katmanı yüklenemedi")

        if self.midi.is_open:
            self.led_midi.set_color(C_GREEN)
            label = self.midi.target_label
            self.midi_value.setText(("IAC Sürücüsü Aktif — " + label) if "iac" in label.lower()
                                    else f"Aktif — {label}")
        else:
            self.led_midi.set_color(C_RED)
            self.midi_value.setText("Port Kapalı")

        if not self.engine.running and self.stop_btn.isEnabled():
            self._sync_buttons()

    def _ui_tick(self) -> None:
        # 1) Log kuyruğunu boşalt
        log = self.engine.log
        lines = []
        while log and len(lines) < 400:
            ts, text, kind = log.popleft()
            color = LOG_COLORS.get(kind, C_TEXT)
            lines.append(f'<span style="color:{C_DIM}">{ts}</span>&nbsp;&nbsp;'
                         f'<span style="color:{color}">{html.escape(text)}</span>')
        if lines:
            sb = self.log_view.verticalScrollBar()
            at_bottom = sb.value() >= sb.maximum() - 4
            for ln in lines[-150:]:
                self.log_view.appendHtml(ln)
            if at_bottom:
                sb.setValue(sb.maximum())

        # 2) Canlı görselleştirme (köprü kapalıyken önizleme)
        if self.engine.running:
            live = self.engine.live
            active = True
        elif self.gamepad is not None:
            with _pool():
                snap = self.gamepad.poll()
            if snap.connected:
                d1_cc, d2_cc, d1_pct, d2_pct, active_deck = config.left_stick_to_dual_cfx(
                    snap.axes.get("LX", 0.0), snap.axes.get("LY", 0.0)
                )
                f1_cc, f2_cc, f1_pct, f2_pct, fx_deck = config.right_stick_to_dual_fx(
                    snap.axes.get("RX", 0.0), snap.axes.get("RY", 0.0)
                )
                midi = {
                    "LX": d1_cc,
                    "RX_CFX": d2_cc,
                    "LY": f1_cc,
                    "RY": f2_cc,
                    "LT": config.trigger_to_midi(snap.axes.get("LT", 0.0)),
                    "RT": config.trigger_to_midi(snap.axes.get("RT", 0.0)),
                }
            else:
                midi, d1_pct, d2_pct, active_deck = {}, 0, 0, 0
                f1_pct, f2_pct, fx_deck = 0, 0, 0
            live = {
                "connected": snap.connected,
                "axes": snap.axes,
                "midi": midi,
                "buttons": snap.buttons,
                "stems_muted": {},
                "fx1_active": self.engine.fx1_active,
                "cfx_active": self.engine.cfx_active,
                "cfx_slot": self.engine.cfx_slot,
                "cfx_deck1_pct": d1_pct,
                "cfx_deck2_pct": d2_pct,
                "cfx_active_deck": active_deck,
                "cfx_hold_locked": self.engine.cfx_hold_locked,
                "fx_deck1_pct": f1_pct,
                "fx_deck2_pct": f2_pct,
                "fx_active_deck": fx_deck,
                "fx_hold_locked": self.engine.fx_hold_locked,
            }
            active = False
        else:
            live = {
                "connected": False,
                "axes": {},
                "midi": {},
                "buttons": {},
                "stems_muted": {},
                "fx1_active": self.engine.fx1_active,
                "cfx_active": self.engine.cfx_active,
                "cfx_slot": self.engine.cfx_slot,
                "cfx_deck1_pct": 0,
                "cfx_deck2_pct": 0,
                "cfx_active_deck": 0,
                "cfx_hold_locked": False,
            }
            active = False

        axes = live.get("axes", {})
        midi = live.get("midi", {})
        buttons = live.get("buttons", {})
        stems_muted = live.get("stems_muted", {})
        fx1_active = bool(live.get("fx1_active", False))
        cfx_active = bool(live.get("cfx_active", False))
        cfx_slot = str(live.get("cfx_slot", self.engine.cfx_slot))
        d1_pct = int(live.get("cfx_deck1_pct", 0))
        d2_pct = int(live.get("cfx_deck2_pct", 0))
        active_deck = int(live.get("cfx_active_deck", 0))
        hold_locked = bool(live.get("cfx_hold_locked", False))
        on = active and live.get("connected", False)

        self._update_cfx_bar_visuals(cfx_slot, cfx_active)
        self.left_pad.set_state(axes, midi, buttons, d1_pct, d2_pct, active_deck, hold_locked, on)
        self.right_pad.set_state(axes, midi, buttons,
                                 int(live.get("fx_deck1_pct", 0)), int(live.get("fx_deck2_pct", 0)),
                                 int(live.get("fx_active_deck", 0)), bool(live.get("fx_hold_locked", False)), on)
        self.lt_bar.set_state(midi, on)
        self.rt_bar.set_state(midi, on)
        self.btn_panel.set_state(
            buttons,
            stems_muted,
            live.get("connected", False),
            fx1_active=fx1_active,
            cfx_active=cfx_active,
            cfx_slot=cfx_slot,
            banner=self.engine.active_banner(),
            learn_mode=self.engine.learn_mode,
        )

        self.stat_label.setText(f"{self.engine.loop_hz:4.1f} Hz · {self.engine.msg_count} mesaj")

    # ------------------------------------------------------------------ #
    def closeEvent(self, event) -> None:
        self.ui_timer.stop()
        self.status_timer.stop()
        self.engine.stop()
        self.midi.dispose()
        super().closeEvent(event)


# --------------------------------------------------------------------------- #
def run() -> int:
    QApplication.setApplicationName(config.APP_NAME)
    QApplication.setApplicationDisplayName(config.APP_NAME)
    QApplication.setOrganizationName("Xbox2MIDI")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in ((QPalette.Window, C_BG0), (QPalette.Base, C_BG1), (QPalette.Text, C_TEXT),
                      (QPalette.WindowText, C_TEXT), (QPalette.Button, C_BG1),
                      (QPalette.ButtonText, C_TEXT), (QPalette.Highlight, C_CYAN),
                      (QPalette.ToolTipBase, C_BG1), (QPalette.ToolTipText, C_TEXT)):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)
    icon_path = resource_path("assets", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.resize(1160, 960)
    win.show()
    win.raise_()
    win.activateWindow()
    return app.exec()
