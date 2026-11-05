"""
Xbox2MIDI DJ - Oyun kumandası girdisi (macOS GameController.framework / PyObjC).

Neden GameController.framework?
  * Apple'ın Xbox Wireless Controller için resmi sürücü katmanıdır
    (Bluetooth ve USB-C/kablolu bağlantı).
  * `shouldMonitorBackgroundEvents` sayesinde Rekordbox ön plandayken bile
    girdiler okunmaya devam eder (SDL/pygame'de en sık yaşanan sorun budur).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

try:
    import objc  # noqa: F401
    import GameController as GC
    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - yalnızca bozuk kurulumda
    GC = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


@dataclass
class ControllerInfo:
    connected: bool = False
    name: str = ""
    category: str = ""
    battery: Optional[float] = None   # 0..1
    charging: bool = False


@dataclass
class InputSnapshot:
    connected: bool
    axes: Dict[str, float] = field(default_factory=dict)
    buttons: Dict[str, bool] = field(default_factory=dict)


_EMPTY = InputSnapshot(False)


def _pressed(el) -> bool:
    return bool(el is not None and el.isPressed())


class GameControllerInput:
    """Bağlı ilk 'extended gamepad' uyumlu kumandayı okur."""

    REFRESH_SEC = 0.5

    def __init__(self) -> None:
        if GC is None:
            raise RuntimeError(
                "GameController framework yüklenemedi. "
                f"(pyobjc-framework-GameController kurulu mu?) Ayrıntı: {_IMPORT_ERROR}"
            )
        self._ctrl = None
        self._last_refresh = 0.0
        self._lock = threading.Lock()
        self.enable_background_monitoring()

    # ------------------------------------------------------------------ #
    @staticmethod
    def enable_background_monitoring() -> bool:
        """Uygulama arka plandayken (Rekordbox öndeyken) girdileri almaya devam et."""
        if GC is None:
            return False
        cls = GC.GCController
        try:
            if cls.respondsToSelector_("setShouldMonitorBackgroundEvents:"):
                cls.setShouldMonitorBackgroundEvents_(True)
                return True
        except Exception:
            pass
        return False

    def _pick(self):
        best = None
        for c in GC.GCController.controllers() or []:
            if c.extendedGamepad() is None:
                continue
            name = (c.vendorName() or "").lower()
            if best is None or "xbox" in name:
                best = c
                if "xbox" in name:
                    break
        return best

    def _refresh(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_refresh < self.REFRESH_SEC:
            return
        with self._lock:
            self._last_refresh = now
            current = list(GC.GCController.controllers() or [])
            if self._ctrl is None or self._ctrl not in current or self._ctrl.extendedGamepad() is None:
                self._ctrl = self._pick()

    # ------------------------------------------------------------------ #
    def info(self) -> ControllerInfo:
        self._refresh(force=True)
        c = self._ctrl
        if c is None:
            return ControllerInfo()
        info = ControllerInfo(True, str(c.vendorName() or "Oyun Kumandası"),
                              str(c.productCategory() or "") if c.respondsToSelector_("productCategory") else "")
        try:
            bat = c.battery() if c.respondsToSelector_("battery") else None
            if bat is not None:
                info.battery = float(bat.batteryLevel())
                info.charging = int(bat.batteryState()) == 1  # GCDeviceBatteryStateCharging
        except Exception:
            pass
        return info

    def poll(self) -> InputSnapshot:
        self._refresh()
        c = self._ctrl
        if c is None:
            return _EMPTY
        gp = c.extendedGamepad()
        if gp is None:
            self._ctrl = None
            return _EMPTY

        ls = gp.leftThumbstick()
        rs = gp.rightThumbstick()
        dp = gp.dpad()
        axes = {
            "LX": float(ls.xAxis().value()),
            "LY": float(ls.yAxis().value()),
            "RX": float(rs.xAxis().value()),
            "RY": float(rs.yAxis().value()),
            "LT": float(gp.leftTrigger().value()),
            "RT": float(gp.rightTrigger().value()),
        }
        buttons = {
            "A": _pressed(gp.buttonA()),
            "B": _pressed(gp.buttonB()),
            "X": _pressed(gp.buttonX()),
            "Y": _pressed(gp.buttonY()),
            "LB": _pressed(gp.leftShoulder()),
            "RB": _pressed(gp.rightShoulder()),
            "UP": _pressed(dp.up()),
            "DOWN": _pressed(dp.down()),
            "LEFT": _pressed(dp.left()),
            "RIGHT": _pressed(dp.right()),
            "L3": _pressed(gp.leftThumbstickButton()),
            "R3": _pressed(gp.rightThumbstickButton()),
            "MENU": _pressed(gp.buttonMenu()),
            "VIEW": _pressed(gp.buttonOptions()),
        }
        return InputSnapshot(True, axes, buttons)
