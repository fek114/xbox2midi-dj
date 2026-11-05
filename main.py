#!/usr/bin/env python3
"""
Xbox2MIDI DJ — giriş noktası.

Çalıştırma:  run.command dosyasına çift tıklayın  (veya derlenmiş .app)
"""
from __future__ import annotations

import os
import sys

_ACTIVITY = None  # App Nap engelleyici referansı (GC'ye gitmesin)


def _set_process_name() -> None:
    """Menü çubuğu ve Dock'ta 'Python' yerine uygulama adını göster."""
    try:
        from Foundation import NSBundle
        from xbox2midi.config import APP_NAME
        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info is not None and info.get("CFBundleName") in (None, "Python", "python3", "Python3"):
            info["CFBundleName"] = APP_NAME
    except Exception:
        pass


def _disable_app_nap() -> None:
    """
    macOS App Nap, arka plandaki uygulamaların zamanlayıcılarını kısar.
    Rekordbox öndeyken MIDI gecikmesi oluşmaması için 'latency critical'
    aktivitesi başlatılır.
    """
    global _ACTIVITY
    try:
        from Foundation import NSProcessInfo
        NSActivityUserInitiated = 0x00FFFFFF
        NSActivityLatencyCritical = 0xFF00000000
        opts = NSActivityUserInitiated | NSActivityLatencyCritical
        _ACTIVITY = NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
            opts, "Xbox2MIDI DJ gerçek zamanlı MIDI köprüsü")
    except Exception:
        _ACTIVITY = None


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    if sys.platform != "darwin":
        print("Xbox2MIDI DJ yalnızca macOS üzerinde çalışır.", file=sys.stderr)
        return 1
    _set_process_name()
    _disable_app_nap()
    from xbox2midi.gui import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
