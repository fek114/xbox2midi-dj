"""
Xbox2MIDI DJ - Köprü motoru (60 FPS worker thread) — Adım 1: XDJ-AZ Sound Color FX (CFX) Mimarisi.

Akış (her karede):
  1. Sol Analog Çubuk (Tek Çubukla Çift Deck CFX Knob — Seçenek 1):
       * Sol Yarı (LX < -0.20) -> Deck 1 CFX (B00A / CFXParameterCH1):
           Sol Aşağı = %0 (MIDI 64 - Saat 12 Nötr)
           Sol Orta (90°) = %50 (MIDI 96 - Saat 2.5)
           Sol Yukarı = %100 Full (MIDI 127 - Saat 5)
       * Sağ Yarı (LX > +0.20) -> Deck 2 CFX (B00C / CFXParameterCH2):
           Sağ Aşağı = %0 (MIDI 64 - Saat 12 Nötr)
           Sağ Orta (90°) = %50 (MIDI 96 - Saat 2.5)
           Sağ Yukarı = %100 Full (MIDI 127 - Saat 5)
       * Kol Merkezdeyken -> Her iki Deck de %0 (MIDI 64) konumunda kilitlenir.
       * ÖNEMLİ: Analoğu hareket ettirmek kendi başına CFX On/Off yapmaz!
  2. LB (Sol Tampon) = DUB ECHO (Bas-Aç / Bas-Kapat Toggle)
     RB (Sağ Tampon) = NOISE (Bas-Aç / Bas-Kapat Toggle)
       * Rekordbox CFX listesinde Dub Echo (2. sıra) ile Noise (4. sıra) arasında
         CFXSelect (904A) ve CFXSelectBack (904B) ile 2 adım gidip CFXOn (9048) şalterini
         otomatik yönetir.
"""
from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from . import config
from . import midi_out as mo
from .controller import GameControllerInput

try:
    import objc
    _pool = objc.autorelease_pool
except Exception:  # pragma: no cover
    from contextlib import nullcontext as _pool  # type: ignore

LogEntry = Tuple[str, str, str]  # (zaman, metin, tür)


class BridgeEngine:
    def __init__(self, midi: mo.MidiOut, gamepad: Optional[GameControllerInput]) -> None:
        self.midi = midi
        self.gamepad = gamepad
        self.log: Deque[LogEntry] = deque(maxlen=4000)
        self.log_analog = True

        # --- XDJ-AZ CFX Durum Takibi (LB = DUB ECHO, RB = NOISE) ---
        # Rekordbox başlangıç CFX seçimi: "DUB_ECHO" (2. sıra) veya "NOISE" (4. sıra)
        self.cfx_slot: str = "DUB_ECHO"
        self.cfx_active: bool = False         # 9048 (CFX On) şu an açık mı?
        self.fx1_active: bool = False         # 9047 (FX1-1 On) şu an açık mı?
        self.learn_mode: bool = False         # [🎯 Rekordbox MIDI Learn Modu]

        # --- L3 ile Sol Analog CFX Sabitleme (Hold / Lock) ---
        self.cfx_hold_locked: bool = False
        self._locked_d1_cc: int = config.STICK_CENTER
        self._locked_d2_cc: int = config.STICK_CENTER
        self._locked_d1_pct: int = 0
        self._locked_d2_pct: int = 0
        self._locked_deck: int = 0

        # --- R3 ile Sağ Analog FX Sabitleme (Hold / Lock) ---
        self.fx_hold_locked: bool = False
        self._locked_fx_d1_cc: int = 0
        self._locked_fx_d2_cc: int = 0
        self._locked_fx_d1_pct: int = 0
        self._locked_fx_d2_pct: int = 0
        self._locked_fx_deck: int = 0

        # --- Arayüz Bildirim Banner'ı ---
        self.banner_text: str = ""
        self.banner_kind: str = "ok"
        self.banner_until: float = 0.0

        self.live: Dict = {
            "connected": False,
            "axes": {},
            "midi": {},
            "buttons": {},
            "stems_muted": {},
            "fx1_active": False,
            "cfx_active": False,
            "cfx_slot": self.cfx_slot,
            "cfx_deck1_pct": 0,
            "cfx_deck2_pct": 0,
            "cfx_active_deck": 0,
            "cfx_hold_locked": False,
            "fx_deck1_pct": 0,
            "fx_deck2_pct": 0,
            "fx_active_deck": 0,
            "fx_hold_locked": False,
        }
        self.loop_hz = 0.0
        self.msg_count = 0

        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sched_lock = threading.Lock()
        self._scheduled: List[Tuple[float, List[tuple], str]] = []
        self._last_cc: Dict[int, int] = {}
        self._held: Dict[str, bool] = {}
        self._stem_muted: Dict[str, bool] = {k: False for k in config.STEM_TOGGLE_KEYS}
        self._reset_pulsed_notes: Set[int] = set()

    # ------------------------------------------------------------------ #
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def emit(self, text: str, kind: str = "info") -> None:
        self.log.append((time.strftime("%H:%M:%S"), text, kind))

    def set_banner(self, text: str, kind: str = "ok", duration: float = 2.8) -> None:
        self.banner_text = text
        self.banner_kind = kind
        self.banner_until = time.monotonic() + duration

    def active_banner(self) -> Optional[Tuple[str, str]]:
        if self.banner_text and time.monotonic() < self.banner_until:
            return (self.banner_text, self.banner_kind)
        return None

    # ------------------------------------------------------------------ #
    def _schedule_after(self, delay_sec: float, msgs: List[tuple], tag: str = "") -> None:
        if self.running:
            with self._sched_lock:
                self._scheduled.append((time.perf_counter() + delay_sec, list(msgs), tag))
        else:
            def _later() -> None:
                time.sleep(delay_sec)
                self._flush(list(msgs), tag)
            threading.Thread(target=_later, daemon=True).start()

    def _drain_scheduled(self) -> None:
        now = time.perf_counter()
        due: List[Tuple[List[tuple], str]] = []
        with self._sched_lock:
            remain = []
            for when, msgs, tag in self._scheduled:
                if now >= when:
                    due.append((msgs, tag))
                else:
                    remain.append((when, msgs, tag))
            self._scheduled = remain
        for msgs, tag in due:
            self._flush(msgs, tag)

    # ------------------------------------------------------------------ #
    #  XDJ-AZ CFX Seçici & Bas-Aç / Bas-Kapat (Toggle) Motoru
    # ------------------------------------------------------------------ #
    def sync_cfx_state(self, slot: str = "DUB_ECHO", active: bool = False) -> None:
        """
        Kullanıcı Rekordbox'ta fareyle CFX'i değiştirdiyse tek tıkla
        uygulamanın iç durumunu Rekordbox ile senkronize eder (MIDI göndermeden).
        """
        self.cfx_slot = "NOISE" if slot == "NOISE" else "DUB_ECHO"
        self.cfx_active = bool(active)
        slot_label = "NOISE" if self.cfx_slot == "NOISE" else "DUB ECHO"
        state_label = "AÇIK" if self.cfx_active else "KAPALI"
        self.set_banner(
            f"🔄 CFX SENKRONLANDI: Seçili Efekt = {slot_label} ({state_label})",
            "ok",
            2.4,
        )
        self.emit(
            f"🔄 [CFX Senkron] Rekordbox referansı '{slot_label} ({state_label})' olarak eşitlendi.",
            "ok",
        )

    def trigger_cfx_button(self, target_slot: str) -> None:
        """
        XDJ-AZ Tarzı LB (DUB_ECHO) ve RB (NOISE) Bas-Aç / Bas-Kapat (Toggle) Mantığı:
          * Eğer hedef efekt zaten seçiliyse:
              - Sadece 9048 (CFX On) darbesi göndererek efekti AÇAR veya KAPATIR.
          * Eğer diğer efekt seçiliyse (Örn: Dub Echo'dan Noise'a veya Noise'dan Dub Echo'ya):
              - Eğer CFX o an açıksa önce 9048 ile CFX'i kapatır (aradaki Sweep efekti duyulmasın diye).
              - Ardından 2 adım CFXSelect (904A, Dub Echo -> Noise) veya
                2 adım CFXSelectBack (904B, Noise -> Dub Echo) gönderir.
              - Son olarak 9048 (CFX On) darbesi göndererek yeni efekti AÇIK konuma getirir!
        """
        if not self.midi.is_open:
            self.emit("MIDI portu kapalı — CFX komutu gönderilemedi.", "err")
            return

        target = "NOISE" if target_slot == "NOISE" else "DUB_ECHO"
        target_name = "NOISE" if target == "NOISE" else "DUB ECHO"
        btn_name = "RB (Sağ Tampon)" if target == "NOISE" else "LB (Sol Tampon)"

        # Önceki bekleyen CFX adımlarını temizle
        with self._sched_lock:
            self._scheduled = [
                (w, m, t) for (w, m, t) in self._scheduled if "CFX-STEP" not in t
            ]

        # Durum 1: Zaten aynı CFX efektindeyiz -> Doğrudan Bas-Aç / Bas-Kapat (9048 Toggle)
        if self.cfx_slot == target:
            self.cfx_active = not self.cfx_active
            self._flush([mo.note_on(config.NOTE_CFX_ON)], f"  · CFX {target_name} {'ON' if self.cfx_active else 'OFF'}")
            self._schedule_after(0.035, [mo.note_off(config.NOTE_CFX_ON)], "  · CFX-STEP latch")

            state_str = "AÇIK (ON)" if self.cfx_active else "KAPALI (OFF)"
            self.set_banner(
                f"🎛 {btn_name} → CFX {target_name}: {state_str}",
                "ok" if self.cfx_active else "warn",
                2.2,
            )
            self.emit(
                f"🎛 [XDJ-AZ CFX] {btn_name} → {target_name} {state_str} (9048 darbesi gönderildi)",
                "ok" if self.cfx_active else "info",
            )
            return

        # Durum 2: Diğer CFX efektine geçiş yapılıyor (Dub Echo <-> Noise, 3 adım)
        # Rekordbox Menü Sırası:
        #   [1] FILTER, [2] JET, [3] CRUSH, [4] NOISE, [5] PITCH, [6] SPACE, [7] DUB ECHO, [8] SWEEP, [9] GATE COMP
        # Dolayısıyla:
        #   * DUB ECHO -> NOISE: 3 adım YUKARI / GERİ -> CFXSelectBack (904B)
        #   * NOISE -> DUB ECHO: 3 adım AŞAĞI / İLERİ -> CFXSelect (904A)
        if target == "NOISE":
            step_note = config.NOTE_CFX_SELECT_BACK   # 904B (Yukarı -> Noise)
            step_hex = "904B"
        else:
            step_note = config.NOTE_CFX_SELECT_NEXT   # 904A (Aşağı -> Dub Echo)
            step_hex = "904A"
        t_offset = 0.0

        # Eğer mevcut CFX açıksa, aradaki efektlerin sesini duymamak ve Rekordbox'ın
        # açık/kapalı durumunu %100 kesinleştirmek için önce mevcut CFX'i kapatıyoruz:
        if self.cfx_active:
            self._flush([mo.note_on(config.NOTE_CFX_ON)], "  · CFX-STEP pre-off")
            self._schedule_after(0.025, [mo.note_off(config.NOTE_CFX_ON)], "  · CFX-STEP pre-off")
            t_offset = 0.045

        # 3 adım yukarı (SelectBack) veya 3 adım aşağı (SelectNext)
        for step_idx in range(config.CFX_SELECT_STEPS):
            t_on = t_offset + step_idx * 0.045
            t_off = t_on + 0.022
            if t_on == 0.0:
                self._flush([mo.note_on(step_note)], f"  · CFX-STEP {step_hex} #{step_idx + 1}")
            else:
                self._schedule_after(t_on, [mo.note_on(step_note)], f"  · CFX-STEP {step_hex} #{step_idx + 1}")
            self._schedule_after(t_off, [mo.note_off(step_note)], "  · CFX-STEP rel")

        # Seçim tamamlandıktan hemen sonra yeni CFX'i AÇ (9048 ON)
        t_final_on = t_offset + config.CFX_SELECT_STEPS * 0.045 + 0.015
        self._schedule_after(t_final_on, [mo.note_on(config.NOTE_CFX_ON)], f"  · CFX-STEP {target_name} ON")
        self._schedule_after(t_final_on + 0.035, [mo.note_off(config.NOTE_CFX_ON)], "  · CFX-STEP latch")

        self.cfx_slot = target
        self.cfx_active = True
        self.set_banner(
            f"🎛 {btn_name} → CFX {target_name} SEÇİLDİ VE AÇILDI ({step_hex}x3 + 9048)",
            "ok",
            2.5,
        )
        self.emit(
            f"🎛 [XDJ-AZ CFX] {btn_name} → {target_name} seçildi ({step_hex} x3) ve CFX AÇILDI (9048)",
            "ok",
        )

    def trigger_fx_button(self) -> None:
        """
        MENU Tuşu ile Beat FX On/Off Bas-Aç / Bas-Kapat (Toggle):
        Rekordbox'ta seçili olan Beat FX ünitesini (9047) tek tıkla açar/kapatır.
        """
        if not self.midi.is_open:
            self.emit("MIDI portu kapalı — FX komutu gönderilemedi.", "err")
            return

        self.fx1_active = not self.fx1_active
        n1, n2 = config.NOTE_FX_ON, config.NOTE_FX2_ON  # 9047 (FX1-1On) + 904D (FX2-1On)
        self._flush([mo.note_on(n1), mo.note_on(n2)], f"  · BEAT FX {'ON' if self.fx1_active else 'OFF'}")
        self._schedule_after(0.035, [mo.note_off(n1), mo.note_off(n2)], "  · FX-STEP latch")

        state_str = "AÇIK (ON)" if self.fx1_active else "KAPALI (OFF)"
        self.set_banner(
            f"🎛 MENU → BEAT FX: {state_str} (9047 Toggle)",
            "ok" if self.fx1_active else "warn",
            2.2,
        )
        self.emit(
            f"🎛 [Beat FX] Menu tuşu → Beat FX {state_str} (9047 darbesi gönderildi)",
            "ok" if self.fx1_active else "info",
        )

    # ------------------------------------------------------------------ #
    #  Sniper MIDI Learn: Tek Tıkla Rekordbox'a İzole Sinyal Gönderme
    # ------------------------------------------------------------------ #
    def send_learn_signal(self, hex_code: str) -> bool:
        """
        Kullanıcı 'REKORDBOX MIDI IN HIZLI SÖZLÜK' üzerindeki bir kutucuğa
        tıkladığında sadece o kontrolün MIDI kodunu izole paket olarak gönderir:
          * Eksen (B0xx): B0xx 40 -> B0xx 60 -> B0xx 7F -> B0xx 40 süpürmesi
          * Buton (90xx): 90xx 7F -> 90xx 00 darbesi
        """
        if not self.midi.is_open:
            self.emit(f"MIDI portu kapalı — {hex_code} gönderilemedi.", "err")
            return False

        item = config.ITEM_BY_HEX.get(hex_code.upper())
        if item is None:
            return False

        if isinstance(item, config.AxisMap):
            cc_num = item.cc
            m0 = mo.cc(cc_num, 0x40)
            m1 = mo.cc(cc_num, 0x60)
            m2 = mo.cc(cc_num, 0x7F)
            m_rest = mo.cc(cc_num, item.rest_value)
            self._flush([m0], "  · 🎯 LEARN [40]")
            self._schedule_after(0.030, [m1], "  · 🎯 LEARN [60]")
            self._schedule_after(0.060, [m2], "  · 🎯 LEARN [7F]")
            self._schedule_after(0.140, [m_rest], "  · 🎯 LEARN [Rest=64]")

            self.set_banner(
                f"🎯 MIDI LEARN GÖNDERİLDİ: {item.hex_code} ({item.label}) → {item.rekordbox_cmd}",
                "ok",
                2.6,
            )
            self.emit(
                f"🎯 [Sniper MIDI Learn] {item.hex_code} ({item.label}) → B0{cc_num:02X} süpürmesi gönderildi.",
                "ok",
            )
            return True

        note_num = item.note
        m_on = mo.note_on(note_num)
        m_off = mo.note_off(note_num)
        self._flush([m_on], "  · 🎯 LEARN [7F]")
        self._schedule_after(0.045, [m_off], "  · 🎯 LEARN [00]")

        self.set_banner(
            f"🎯 MIDI LEARN GÖNDERİLDİ: {item.hex_code} ({item.label}) → {item.rekordbox_cmd} [7F→00]",
            "ok",
            2.6,
        )
        self.emit(
            f"🎯 [Sniper MIDI Learn] {item.hex_code} ({item.label}) → 90{note_num:02X} 7F -> 00 izole paketi gönderildi.",
            "ok",
        )
        return True

    # ------------------------------------------------------------------ #
    def start(self) -> bool:
        if self.running:
            return True
        if self.gamepad is None:
            self.emit("GameController katmanı kullanılamıyor — köprü başlatılamadı.", "err")
            return False
        if not self.midi.is_open:
            self.emit("MIDI çıkış portu kapalı — köprü başlatılamadı.", "err")
            return False
        self._stop.clear()
        self._last_cc.clear()
        self._held.clear()
        with self._sched_lock:
            self._scheduled.clear()
        self.cfx_hold_locked = False
        self.fx_hold_locked = False
        self._stem_muted = {k: False for k in config.STEM_TOGGLE_KEYS}
        self._reset_pulsed_notes.clear()
        self._thread = threading.Thread(target=self._run, name="Xbox2MIDI-Worker", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 1.0) -> None:
        t = self._thread
        if t is None:
            return
        self._stop.set()
        t.join(timeout)
        self._thread = None

    # ------------------------------------------------------------------ #
    def _release_all(self) -> List[tuple]:
        """Tüm çıkışları güvenli dinlenme konumuna getirir (CFX 64, tetik 0, Note Off)."""
        msgs: List[tuple] = []
        for axis in config.AXES:
            if self._last_cc.get(axis.cc, axis.rest_value) != axis.rest_value:
                msgs.append(mo.cc(axis.cc, axis.rest_value))
        for key, down in self._held.items():
            if down and key in config.BUTTON_BY_KEY:
                msgs.append(mo.note_off(config.BUTTON_BY_KEY[key].note))
        for note in self._reset_pulsed_notes:
            msgs.append(mo.note_off(note))
        self._last_cc.clear()
        self._held.clear()
        self.cfx_hold_locked = False
        self.fx_hold_locked = False
        self._reset_pulsed_notes.clear()
        return msgs

    def _live_dict(self, snap, midi_vals, d1_pct, d2_pct, active_deck,
                   f1_pct, f2_pct, fx_deck) -> Dict:
        return {
            "connected": True,
            "axes": dict(snap.axes),
            "midi": midi_vals,
            "buttons": dict(snap.buttons),
            "stems_muted": dict(self._stem_muted),
            "fx1_active": self.fx1_active,
            "cfx_active": self.cfx_active,
            "cfx_slot": self.cfx_slot,
            "cfx_deck1_pct": d1_pct,
            "cfx_deck2_pct": d2_pct,
            "cfx_active_deck": active_deck,
            "cfx_hold_locked": self.cfx_hold_locked,
            "fx_deck1_pct": f1_pct,
            "fx_deck2_pct": f2_pct,
            "fx_active_deck": fx_deck,
            "fx_hold_locked": self.fx_hold_locked,
        }

    def _process(self, snap) -> List[tuple]:
        msgs: List[tuple] = []
        midi_vals: Dict[str, int] = {}

        # 1) Sol Analog -> Çift Deck CFX Knob (Aşağı=%0 [64], Orta=%50 [96], Yukarı=%100 [127])
        d1_cc, d2_cc, d1_pct, d2_pct, active_deck = config.left_stick_to_dual_cfx(
            snap.axes.get("LX", 0.0), snap.axes.get("LY", 0.0)
        )
        if self.cfx_hold_locked:
            if active_deck == 0:
                d1_cc, d2_cc = self._locked_d1_cc, self._locked_d2_cc
                d1_pct, d2_pct = self._locked_d1_pct, self._locked_d2_pct
                active_deck = self._locked_deck
            else:
                self._locked_d1_cc, self._locked_d2_cc = d1_cc, d2_cc
                self._locked_d1_pct, self._locked_d2_pct = d1_pct, d2_pct
                self._locked_deck = active_deck

        # 2) Sağ Analog -> Çift Deck Beat FX Depth (Aşağı=%0 [0], Orta=%50 [64], Yukarı=%100 [127])
        f1_cc, f2_cc, f1_pct, f2_pct, fx_deck = config.right_stick_to_dual_fx(
            snap.axes.get("RX", 0.0), snap.axes.get("RY", 0.0)
        )
        if self.fx_hold_locked:
            if fx_deck == 0:
                f1_cc, f2_cc = self._locked_fx_d1_cc, self._locked_fx_d2_cc
                f1_pct, f2_pct = self._locked_fx_d1_pct, self._locked_fx_d2_pct
                fx_deck = self._locked_fx_deck
            else:
                self._locked_fx_d1_cc, self._locked_fx_d2_cc = f1_cc, f2_cc
                self._locked_fx_d1_pct, self._locked_fx_d2_pct = f1_pct, f2_pct
                self._locked_fx_deck = fx_deck

        midi_vals["LX"] = d1_cc       # B00A -> CFXParameterCH1
        midi_vals["RX_CFX"] = d2_cc   # B00C -> CFXParameterCH2
        midi_vals["LY"] = f1_cc       # B00B -> FX1-1 LevelDepth
        midi_vals["RY"] = f2_cc       # B00D -> FX2-1 LevelDepth
        midi_vals["LT"] = config.trigger_to_midi(snap.axes.get("LT", 0.0))
        midi_vals["RT"] = config.trigger_to_midi(snap.axes.get("RT", 0.0))

        if self.learn_mode:
            self.live = self._live_dict(snap, midi_vals, d1_pct, d2_pct, active_deck,
                                        f1_pct, f2_pct, fx_deck)
            return msgs

        # 3) Eksen CC çıkışları — analog hareket ASLA kendi başına On/Off göndermez
        for key in ("LX", "RX_CFX", "LY", "RY", "LT", "RT"):
            axis = config.AXIS_BY_KEY[key]
            val = midi_vals[key]
            if self._last_cc.get(axis.cc) != val:
                self._last_cc[axis.cc] = val
                msgs.append(mo.cc(axis.cc, val))

        # 4) Dijital Butonlar
        for btn in config.BUTTONS:
            if btn.key not in snap.buttons:
                continue  # Sanal butonlar (CFX_ON, CFX_NEXT, CFX_BACK, FX2_ON) makrolarla sürülür
            down = snap.buttons.get(btn.key, False)
            if down == self._held.get(btn.key, False):
                continue
            self._held[btn.key] = down

            if btn.key == "LB":
                if down:
                    self.trigger_cfx_button("DUB_ECHO")
                continue
            if btn.key == "RB":
                if down:
                    self.trigger_cfx_button("NOISE")
                continue
            if btn.key == "MENU":
                if down:
                    self.trigger_fx_button()
                continue

            if btn.key == "L3":
                if down:
                    if not self.cfx_hold_locked and active_deck in (1, 2):
                        self.cfx_hold_locked = True
                        self._locked_d1_cc, self._locked_d2_cc = d1_cc, d2_cc
                        self._locked_d1_pct, self._locked_d2_pct = d1_pct, d2_pct
                        self._locked_deck = active_deck
                        pct_now = d1_pct if active_deck == 1 else d2_pct
                        self.set_banner(f"🔒 CFX KİLİTLENDİ: Deck {active_deck} = %{pct_now} (Çöz: L3)", "warn", 2.5)
                        self.emit(f"🔒 [L3 Hold] Deck {active_deck} CFX %{pct_now} seviyesinde sabitlendi.", "ok")
                    else:
                        self.cfx_hold_locked = False
                        self.set_banner("🔓 CFX KİLİDİ ÇÖZÜLDÜ", "ok", 2.0)
                        self.emit("🔓 [L3 Hold] Sol Analog CFX kilidi çözüldü.", "info")
                continue

            if btn.key == "R3":
                if down:
                    if not self.fx_hold_locked and fx_deck in (1, 2):
                        self.fx_hold_locked = True
                        self._locked_fx_d1_cc, self._locked_fx_d2_cc = f1_cc, f2_cc
                        self._locked_fx_d1_pct, self._locked_fx_d2_pct = f1_pct, f2_pct
                        self._locked_fx_deck = fx_deck
                        pct_now = f1_pct if fx_deck == 1 else f2_pct
                        self.set_banner(f"🔒 FX KİLİTLENDİ: Deck {fx_deck} = %{pct_now} (Çöz: R3)", "warn", 2.5)
                        self.emit(f"🔒 [R3 Hold] Deck {fx_deck} Beat FX %{pct_now} seviyesinde sabitlendi.", "ok")
                    else:
                        self.fx_hold_locked = False
                        self.set_banner("🔓 FX KİLİDİ ÇÖZÜLDÜ", "ok", 2.0)
                        self.emit("🔓 [R3 Hold] Sağ Analog FX kilidi çözüldü.", "info")
                continue

            # --- D-Pad Sağ: ActivePartReset ---
            if btn.key == config.STEM_RESET_KEY:
                if down:
                    msgs.append(mo.note_on(btn.note))
                    reset_labels: List[str] = []
                    for sk in config.STEM_TOGGLE_KEYS:
                        if self._stem_muted.get(sk, False):
                            sbtn = config.BUTTON_BY_KEY[sk]
                            msgs.append(mo.note_on(sbtn.note))
                            self._reset_pulsed_notes.add(sbtn.note)
                            self._stem_muted[sk] = False
                            reset_labels.append(sbtn.rekordbox_cmd.split()[0])
                    if reset_labels:
                        self.emit(f"[ActivePartReset] Stems sıfırlandı ({', '.join(reset_labels)}) → Orijinal ses", "ok")
                    else:
                        self.emit("[ActivePartReset] Tüm Stems kanalları zaten aktif.", "info")
                else:
                    msgs.append(mo.note_off(btn.note))
                    for note in sorted(self._reset_pulsed_notes):
                        msgs.append(mo.note_off(note))
                    self._reset_pulsed_notes.clear()
                continue

            if btn.key in config.STEM_TOGGLE_KEYS and down:
                self._stem_muted[btn.key] = not self._stem_muted.get(btn.key, False)

            msgs.append(mo.note_on(btn.note) if down else mo.note_off(btn.note))

        self.live = self._live_dict(snap, midi_vals, d1_pct, d2_pct, active_deck,
                                    f1_pct, f2_pct, fx_deck)
        return msgs

    def _flush(self, msgs: List[tuple], tag: str = "") -> None:
        if not msgs:
            return
        self.midi.send(msgs)
        self.msg_count += len(msgs)
        for (status, d1, d2), text in zip(msgs, mo.describe(msgs)):
            kind = status & 0xF0
            if kind == 0xB0:
                if not self.log_analog and not tag:
                    continue
                self.emit(text + tag, "cc")
            elif kind == 0x90 and d2 > 0:
                self.emit(text + tag, "on")
            else:
                self.emit(text + tag, "off")

    def _run(self) -> None:
        period = 1.0 / config.LOOP_HZ
        self.emit(
            f"Köprü başladı → {self.midi.target_label} · Kanal 1 · {config.LOOP_HZ} FPS · "
            "XDJ-AZ CFX Modu (LB=Dub Echo, RB=Noise, Sol Analog=Deck 1/2 CFX Knob)",
            "ok",
        )
        was_connected = False
        frames, t_stat = 0, time.perf_counter()
        next_t = time.perf_counter()
        try:
            while not self._stop.is_set():
                self._drain_scheduled()
                with _pool():
                    snap = self.gamepad.poll()

                if snap.connected:
                    if not was_connected:
                        self.emit(
                            "Kumanda aktif — Deck 1 & Deck 2 CFX topuzları %0 (MIDI 64) konumunda hazır.",
                            "ok",
                        )
                        self._flush(self._process(snap), "  · sync")
                    else:
                        self._flush(self._process(snap))
                    was_connected = True
                elif was_connected:
                    self.emit("Kumanda bağlantısı koptu — tüm kontroller güvenli konuma alındı.", "warn")
                    self._flush(self._release_all(), "  · reset")
                    self.live = {
                        "connected": False,
                        "axes": {},
                        "midi": {},
                        "buttons": {},
                        "stems_muted": {},
                        "fx1_active": False,
                        "cfx_active": self.cfx_active,
                        "cfx_slot": self.cfx_slot,
                        "cfx_deck1_pct": 0,
                        "cfx_deck2_pct": 0,
                        "cfx_active_deck": 0,
                        "cfx_hold_locked": False,
                    }
                    was_connected = False

                frames += 1
                now = time.perf_counter()
                if now - t_stat >= 1.0:
                    self.loop_hz = frames / (now - t_stat)
                    frames, t_stat = 0, now

                next_t += period
                delay = next_t - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_t = time.perf_counter()
        except Exception as exc:  # pragma: no cover
            self.emit(f"Worker hatası: {exc}", "err")
            traceback.print_exc()
        finally:
            try:
                self._flush(self._release_all(), "  · reset")
            except Exception:
                pass
            self.live = {
                "connected": False,
                "axes": {},
                "midi": {},
                "buttons": {},
                "stems_muted": {},
                "fx1_active": False,
                "cfx_active": self.cfx_active,
                "cfx_slot": self.cfx_slot,
                "cfx_deck1_pct": 0,
                "cfx_deck2_pct": 0,
                "cfx_active_deck": 0,
                "cfx_hold_locked": False,
            }
            self.loop_hz = 0.0
            self.emit("Köprü durduruldu — CFX topuzları %0 (MIDI 64) konumuna alındı.", "info")
