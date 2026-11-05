"""
Xbox2MIDI DJ - XDJ-AZ Tarzı Sound Color FX (CFX) & Stems Eşleme Yapılandırması.

Adım 1 (CFX Odaklı Kurgu):
  * Sol Analog Çubuk (Tek Analog ile Çift Deck CFX Knob — Seçenek 1):
      - Sol Yarı (LX < -0.20) -> Deck 1 CFX (B00A / CFXParameterCH1):
          Aşağı Sol = %0 (MIDI 64 - Saat 12 Nötr)
          Orta Sol (90°) = %50 (MIDI 96 - Saat 2.5)
          Yukarı Sol = %100 Full (MIDI 127 - Saat 5)
      - Sağ Yarı (LX > +0.20) -> Deck 2 CFX (B00C / CFXParameterCH2):
          Aşağı Sağ = %0 (MIDI 64 - Saat 12 Nötr)
          Orta Sağ (90°) = %50 (MIDI 96 - Saat 2.5)
          Yukarı Sağ = %100 Full (MIDI 127 - Saat 5)
      - Kol Bırakıldığında (Merkez) -> İki Deck de %0 (MIDI 64) konumuna döner.
      - Analoğa dokunmak kendi başına CFX On/Off yapmaz!
  * LB (Sol Tampon) -> DUB ECHO (Bas-Aç / Bas-Kapat Toggle)
  * RB (Sağ Tampon) -> NOISE (Bas-Aç / Bas-Kapat Toggle)
    (Rekordbox CFX listesinde Dub Echo [2. sıra] ve Noise [4. sıra] arasında
     CFXSelect [904A] / CFXSelectBack [904B] + CFXOn [9048] ile otomatik geçiş yapar).

Tüm MIDI mesajları TEK bir sabit kanal üzerinden gönderilir:
  MIDI Channel 1 (Index 0) — MPE ve round-robin KESİNLİKLE KAPALIDIR.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Union

APP_NAME = "Xbox2MIDI DJ"
APP_VERSION = "2.2.0"
BUNDLE_ID = "com.xbox2midi.dj"

# --------------------------------------------------------------------------- #
#  MIDI
# --------------------------------------------------------------------------- #
MIDI_CHANNEL = 0                 # MIDI Channel 1 (index 0) — SABİT
VIRTUAL_PORT_NAME = "Xbox DJ Port"
VIRTUAL_PORT_UNIQUE_ID = 0x58424458  # "XBDX" — Rekordbox'ın portu her açılışta tanıması için sabit

# Buton bırakıldığında gönderilecek mesaj tipi:
#   "note_on_zero" -> 0x90 nn 00  (Pioneer DDJ / XDJ donanım standardı — Varsayılan)
#   "note_off"     -> 0x80 nn 00  (Standart MIDI Note Off, velocity 0)
NOTE_OFF_STYLE = "note_on_zero"
NOTE_ON_VELOCITY = 127

# --------------------------------------------------------------------------- #
#  Girdi İşleme & XDJ-AZ CFX Dual-Deck Analog Eşikleri
# --------------------------------------------------------------------------- #
LOOP_HZ = 60                     # Worker thread frekansı (60 FPS)
STICK_DEADZONE = 0.06            # Genel analog çubuk ölü bölgesi (±0.06)
STICK_Y_DEADZONE = 0.08          # Y ekseni ölü bölgesi
TRIGGER_DEADZONE = 0.02          # Tetik başlangıç gürültü filtresi
STICK_CENTER = 64                # Rekordbox CFX Nötr / %0 Efekt merkezi (Saat 12 yönü = 64)

# Sol Analog Çift-Deck CFX (Seçenek 1: Aşağı=%0 [64], Orta=%50 [96], Yukarı=%100 [127])
CFX_SIDE_DEADZONE = 0.20         # Sol/Sağ Deck seçimi için yatay eşik (|LX| > 0.20)
CFX_MID_DEADZONE = 0.07          # 90° Sol/Sağ tam ortada %50 (MIDI 96) kilitleme bandı
CFX_Y_FULL_SPAN = 0.72           # Dairesel analog çerçevede kenardan yukarı/aşağı tam menzil

# Rekordbox CFX Seçici Sabitleri:
# Rekordbox menü sırası: FILTER -> JET -> CRUSH -> NOISE (4) -> PITCH -> SPACE -> DUB ECHO (7) -> SWEEP -> GATE COMP
# Dub Echo (7) ile Noise (4) arasında tam 3 adım vardır:
#   * Dub Echo -> Noise: 3 adım YUKARI / GERİ (CFXSelectBack / 904B)
#   * Noise -> Dub Echo: 3 adım AŞAĞI / İLERİ (CFXSelect / 904A)
CFX_SELECT_STEPS = 3             # Dub Echo <-> Noise arası tam 3 adım
NOTE_CFX_ON = 72                 # 9048 -> Rekordbox "CFX On"
NOTE_CFX_SELECT_NEXT = 74        # 904A -> Rekordbox "CFX Select Next" (Aşağı -> Dub Echo)
NOTE_CFX_SELECT_BACK = 75        # 904B -> Rekordbox "CFX Select Back" (Yukarı -> Noise)

NOTE_FX_ON = 71                  # 9047 -> Rekordbox "FX1-1On" (Menu tuşu -> Deck 1 / FX1)
NOTE_FX2_ON = 77                 # 904D -> Rekordbox "FX2-1On" (Menu tuşu -> Deck 2 / FX2)

Y_AXIS_UNIPOLAR = False


@dataclass(frozen=True)
class AxisMap:
    key: str              # Dahili girdi anahtarı ("LX", "LY", "RX", "RY", "LT", "RT")
    cc: int               # MIDI CC numarası
    hex_code: str         # Rekordbox CSV Hex karşılığı (Örn: "B00A")
    label: str            # Kumanda üzerindeki adı
    rekordbox_cmd: str    # Rekordbox fonksiyon adı
    function: str         # Görevi & açıklama
    kind: str             # "cfx_deck1" | "cfx_deck2" | "fx_deck1" | "fx_deck2" | "stick" | "stick_y" | "trigger"
    invert: bool = False

    @property
    def rest_value(self) -> int:
        if self.kind in ("cfx_deck1", "cfx_deck2", "stick"):
            return STICK_CENTER
        if self.kind in ("fx_deck1", "fx_deck2", "trigger"):
            return 0
        if self.kind == "stick_y":
            return 0 if Y_AXIS_UNIPOLAR else STICK_CENTER
        return 0


@dataclass(frozen=True)
class ButtonMap:
    key: str              # Dahili buton anahtarı
    note: int             # MIDI Note numarası
    hex_code: str         # Rekordbox CSV Hex karşılığı (Örn: "903C")
    label: str            # Kumanda üzerindeki adı
    rekordbox_cmd: str    # Rekordbox fonksiyon adı
    function: str         # Görevi & açıklama


# --------------------------------------------------------------------------- #
#  XBOX DJ EŞLEME MATRİSİ (SOL ANALOG: CFX · SAĞ ANALOG: BEAT FX · STEMS · PAD FX)
# --------------------------------------------------------------------------- #
AXES: tuple[AxisMap, ...] = (
    AxisMap(
        key="LX",
        cc=10,
        hex_code="B00A",
        label="Sol Analog (Sol Yarı ↖↙)",
        rekordbox_cmd="CFXParameterCH1 (Deck 1 CFX Knob)",
        function="Deck 1 CFX Knob: Sol Aşağı=%0 (64) ➔ 90° Sol Orta=%50 (96) ➔ Sol Yukarı=%100 Full (127)",
        kind="cfx_deck1",
    ),
    AxisMap(
        key="RX_CFX",
        cc=12,
        hex_code="B00C",
        label="Sol Analog (Sağ Yarı ↗↘)",
        rekordbox_cmd="CFXParameterCH2 (Deck 2 CFX Knob)",
        function="Deck 2 CFX Knob: Sağ Aşağı=%0 (64) ➔ 90° Sağ Orta=%50 (96) ➔ Sağ Yukarı=%100 Full (127)",
        kind="cfx_deck2",
    ),
    AxisMap(
        key="LY",
        cc=11,
        hex_code="B00B",
        label="Sağ Analog (Sol Yarı ↖↙)",
        rekordbox_cmd="FX1-1 LevelDepth (Deck 1 FX)",
        function="Deck 1 Beat FX: Sol Aşağı=%0 (0) ➔ 90° Sol Orta=%50 (64) ➔ Sol Yukarı=%100 Full (127)",
        kind="fx_deck1",
    ),
    AxisMap(
        key="RY",
        cc=13,
        hex_code="B00D",
        label="Sağ Analog (Sağ Yarı ↗↘)",
        rekordbox_cmd="FX2-1 LevelDepth (Deck 2 FX)",
        function="Deck 2 Beat FX: Sağ Aşağı=%0 (0) ➔ 90° Sağ Orta=%50 (64) ➔ Sağ Yukarı=%100 Full (127)",
        kind="fx_deck2",
    ),
    AxisMap(
        key="LT",
        cc=14,
        hex_code="B00E",
        label="LT (Sol Tetik)",
        rekordbox_cmd="CFXParameterMaster",
        function="Sol Tetik (0–127 Unipolar)",
        kind="trigger",
    ),
    AxisMap(
        key="RT",
        cc=15,
        hex_code="B00F",
        label="RT (Sağ Tetik)",
        rekordbox_cmd="FX1-1 LevelDepth (Alternatif)",
        function="Sağ Tetik (0–127 Unipolar)",
        kind="trigger",
    ),
)

BUTTONS: tuple[ButtonMap, ...] = (
    # --- Tampon Tuşları: XDJ-AZ Tarzı CFX DUB ECHO & NOISE (Bas-Aç / Bas-Kapat Toggle) ---
    ButtonMap(
        key="LB",
        note=64,
        hex_code="9040",
        label="LB (L1 · Sol Tampon)",
        rekordbox_cmd="CFX DUB ECHO (Bas-Aç / Bas-Kapat)",
        function="XDJ-AZ CFX: Rekordbox'ta Dub Echo'yu seçer (904A x3) ve CFX On/Off (9048) yapar",
    ),
    ButtonMap(
        key="RB",
        note=65,
        hex_code="9041",
        label="RB (R1 · Sağ Tampon)",
        rekordbox_cmd="CFX NOISE (Bas-Aç / Bas-Kapat)",
        function="XDJ-AZ CFX: Rekordbox'ta Noise'u seçer (904B x3) ve CFX On/Off (9048) yapar",
    ),
    # --- Menu Tuşu: Beat FX On/Off (Bas-Aç / Bas-Kapat Toggle) ---
    ButtonMap(
        key="MENU",
        note=NOTE_FX_ON,
        hex_code="9047",
        label="Menu (≡) / FX On",
        rekordbox_cmd="FX1-1On (Beat FX On/Off)",
        function="Beat FX Ana Şalteri: Seçili efekti açar/kapatır (Bas-Aç / Bas-Kapat Toggle)",
    ),
    ButtonMap(
        key="FX2_ON",
        note=NOTE_FX2_ON,
        hex_code="904D",
        label="FX2 On (Menu ile birlikte)",
        rekordbox_cmd="FX2-1On (Beat FX 2 On/Off)",
        function="Menu tuşu FX1 ile birlikte FX2'yi de açar/kapatır (Deck 2 FX için)",
    ),
    # --- Rekordbox CFX Doğrudan MIDI Komutları (9048, 904A, 904B) ---
    ButtonMap(
        key="CFX_ON",
        note=NOTE_CFX_ON,
        hex_code="9048",
        label="CFX On Şalteri (LB/RB)",
        rekordbox_cmd="CFXOn (CFX Aç/Kapat)",
        function="Rekordbox CFX On/Off ana şalteri (LB ve RB bu sinyali otomatik gönderir)",
    ),
    ButtonMap(
        key="CFX_NEXT",
        note=NOTE_CFX_SELECT_NEXT,
        hex_code="904A",
        label="CFX Select Next (Aşağı ↓)",
        rekordbox_cmd="CFXSelect (Sonraki CFX)",
        function="Rekordbox CFX menüsünde aşağı iner (Noise ➔ Dub Echo için LB kullanır)",
    ),
    ButtonMap(
        key="CFX_BACK",
        note=NOTE_CFX_SELECT_BACK,
        hex_code="904B",
        label="CFX Select Back (Yukarı ↑)",
        rekordbox_cmd="CFXSelectBack (Önceki CFX)",
        function="Rekordbox CFX menüsünde yukarı çıkar (Dub Echo ➔ Noise için RB kullanır)",
    ),
    # --- Stick Tık (L3 / R3) ---
    ButtonMap(
        key="L3",
        note=70,
        hex_code="9046",
        label="L3 (Sol Stick Tık)",
        rekordbox_cmd="CFX Knob Kilitle (Hold)",
        function="Sol Analog CFX değerini o anki yüzdede kilitler / çözer (Hold)",
    ),
    ButtonMap(
        key="R3",
        note=76,
        hex_code="904C",
        label="R3 (Sağ Stick Tık)",
        rekordbox_cmd="FX Level Kilitle (Hold)",
        function="Sağ Analog FX seviyesini o anki konumda kilitler / çözer (Hold)",
    ),
    # --- D-Pad: Stems (Kök) İstasyonu (Deck 1) ---
    ButtonMap(
        key="UP",
        note=66,
        hex_code="9042",
        label="D-Pad Yukarı (↑)",
        rekordbox_cmd="ActivePartVocal (Deck 1)",
        function="Stems: Vokal kanalını (Acapella) aç/kapat",
    ),
    ButtonMap(
        key="LEFT",
        note=68,
        hex_code="9044",
        label="D-Pad Sol (←)",
        rekordbox_cmd="ActivePartInst (Deck 1)",
        function="Stems: Enstrüman kanalını aç/kapat",
    ),
    ButtonMap(
        key="DOWN",
        note=67,
        hex_code="9043",
        label="D-Pad Aşağı (↓)",
        rekordbox_cmd="ActivePartDrums (Deck 1)",
        function="Stems: Davul/Ritim kanalını aç/kapat",
    ),
    ButtonMap(
        key="RIGHT",
        note=69,
        hex_code="9045",
        label="D-Pad Sağ (→)",
        rekordbox_cmd="ActivePartReset (Deck 1)",
        function="Stems: Tüm kanalları sıfırlayıp orijinal sese dön",
    ),
    # --- ABXY: Pad FX 1 İstasyonu (Deck 1) ---
    ButtonMap(
        key="A",
        note=60,
        hex_code="903C",
        label="A Tuşu",
        rekordbox_cmd="PAD1_PadFx1 (PadFX1 Pad1)",
        function="Pad FX 1: Pad 1 (1/4 Roll)",
    ),
    ButtonMap(
        key="B",
        note=61,
        hex_code="903D",
        label="B Tuşu",
        rekordbox_cmd="PAD2_PadFx1 (PadFX1 Pad2)",
        function="Pad FX 1: Pad 2 (1/2 Roll)",
    ),
    ButtonMap(
        key="X",
        note=62,
        hex_code="903E",
        label="X Tuşu",
        rekordbox_cmd="PAD3_PadFx1 (PadFX1 Pad3)",
        function="Pad FX 1: Pad 3 (Reverb Freeze)",
    ),
    ButtonMap(
        key="Y",
        note=63,
        hex_code="903F",
        label="Y Tuşu",
        rekordbox_cmd="PAD4_PadFx1 (PadFX1 Pad4)",
        function="Pad FX 1: Pad 4 (Spiral / Trans)",
    ),
    ButtonMap(
        key="VIEW",
        note=73,
        hex_code="9049",
        label="View (⧉)",
        rekordbox_cmd="ActivePartMuteSolo",
        function="Stems: Mute / Solo mod geçişi",
    ),
)

STEM_TOGGLE_KEYS: tuple[str, ...] = ("UP", "LEFT", "DOWN")
STEM_RESET_KEY: str = "RIGHT"
PADFX_KEYS: tuple[str, ...] = ("A", "B", "X", "Y")

AXIS_BY_KEY = {a.key: a for a in AXES}
AXIS_BY_CC = {a.cc: a for a in AXES}
BUTTON_BY_KEY = {b.key: b for b in BUTTONS}
BUTTON_BY_NOTE = {b.note: b for b in BUTTONS}

ITEM_BY_HEX: Dict[str, Union[AxisMap, ButtonMap]] = {
    **{b.hex_code: b for b in BUTTONS},
    **{a.hex_code: a for a in AXES},
}


# --------------------------------------------------------------------------- #
#  Ölçekleme Fonksiyonları (Saf, Thread-Safe)
# --------------------------------------------------------------------------- #
def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def left_stick_to_dual_cfx(
    lx: float,
    ly: float,
    side_deadzone: float = CFX_SIDE_DEADZONE,
    mid_deadzone: float = CFX_MID_DEADZONE,
    y_span: float = CFX_Y_FULL_SPAN,
) -> Tuple[int, int, int, int, int]:
    """
    Sol Analog Çubuğu (LX, LY) tek çubukla hem Deck 1 hem Deck 2 CFX topuzuna dönüştürür
    (Seçenek 1: Aşağı = %0 [MIDI 64], 90° Orta = %50 [MIDI 96], Yukarı = %100 Full [MIDI 127]).

    Dönüş:
      (deck1_cc, deck2_cc, deck1_pct, deck2_pct, active_deck)
      * active_deck: 0 (Merkez/Bırakıldı), 1 (Sol Yarı - Deck 1), 2 (Sağ Yarı - Deck 2)
      * Rekordbox'ta CFX topuzunun %0 (kapalı/nötr) noktası Saat 12 yönüdür (MIDI 64).
        %50 = MIDI 96 (Saat 2.5 yönü), %100 Full = MIDI 127 (Saat 5 yönü).
    """
    x = _clamp(float(lx), -1.0, 1.0)
    y = _clamp(float(ly), -1.0, 1.0)

    # Kol merkezdeyse (sola veya sağa yatırılmamışsa) her iki Deck de %0 (MIDI 64)
    if abs(x) <= side_deadzone:
        return (STICK_CENTER, STICK_CENTER, 0, 0, 0)

    # Dikey pozisyonu (y) %0..%50..%100 aralığına ölçekle:
    #   |y| <= mid_deadzone -> tam %50 (MIDI 96)
    #   y >= +y_span        -> tam %100 (MIDI 127)
    #   y <= -y_span        -> tam %0 (MIDI 64)
    if abs(y) <= mid_deadzone:
        pct_norm = 0.5
    elif y > 0:
        eff_span = max(0.05, y_span - mid_deadzone)
        t = _clamp((y - mid_deadzone) / eff_span, 0.0, 1.0)
        pct_norm = 0.5 + 0.5 * t
    else:
        eff_span = max(0.05, y_span - mid_deadzone)
        t = _clamp((abs(y) - mid_deadzone) / eff_span, 0.0, 1.0)
        pct_norm = 0.5 - 0.5 * t

    pct = int(round(pct_norm * 100))
    # MIDI 64 (%0) -> 96 (%50) -> 127 (%100)
    cc_val = int(_clamp(round(STICK_CENTER + pct_norm * (127 - STICK_CENTER)), STICK_CENTER, 127))

    if x < 0:
        # Sol Yarı -> Deck 1 CFX (B00A), Deck 2 (B00C) %0'da (64) sabit
        return (cc_val, STICK_CENTER, pct, 0, 1)
    else:
        # Sağ Yarı -> Deck 2 CFX (B00C), Deck 1 (B00A) %0'da (64) sabit
        return (STICK_CENTER, cc_val, 0, pct, 2)


def right_stick_to_dual_fx(
    rx: float,
    ry: float,
    side_deadzone: float = CFX_SIDE_DEADZONE,
    mid_deadzone: float = CFX_MID_DEADZONE,
    y_span: float = CFX_Y_FULL_SPAN,
) -> Tuple[int, int, int, int, int]:
    """
    Sağ Analog Çubuğu (RX, RY) tek çubukla hem Deck 1 hem Deck 2 FX Level/Depth topuzuna dönüştürür
    (Aşağı = %0 [MIDI 0], 90° Orta = %50 [MIDI 64], Yukarı = %100 Full [MIDI 127]).

    Dönüş:
      (deck1_cc, deck2_cc, deck1_pct, deck2_pct, active_deck)
      * active_deck: 0 (Merkez/Bırakıldı), 1 (Sol Yarı - Deck 1 FX), 2 (Sağ Yarı - Deck 2 FX)
      * Beat FX Level/Depth unipolar'dır: %0 = MIDI 0 (Dry), %50 = MIDI 64, %100 = MIDI 127 (Wet).
    """
    x = _clamp(float(rx), -1.0, 1.0)
    y = _clamp(float(ry), -1.0, 1.0)

    # Kol merkezdeyse (sola veya sağa yatırılmamışsa) her iki Deck de %0 (MIDI 0)
    if abs(x) <= side_deadzone:
        return (0, 0, 0, 0, 0)

    # Dikey pozisyonu (y) %0..%50..%100 aralığına ölçekle:
    #   |y| <= mid_deadzone -> tam %50 (MIDI 64)
    #   y >= +y_span        -> tam %100 (MIDI 127)
    #   y <= -y_span        -> tam %0 (MIDI 0)
    if abs(y) <= mid_deadzone:
        pct_norm = 0.5
    elif y > 0:
        eff_span = max(0.05, y_span - mid_deadzone)
        t = _clamp((y - mid_deadzone) / eff_span, 0.0, 1.0)
        pct_norm = 0.5 + 0.5 * t
    else:
        eff_span = max(0.05, y_span - mid_deadzone)
        t = _clamp((abs(y) - mid_deadzone) / eff_span, 0.0, 1.0)
        pct_norm = 0.5 - 0.5 * t

    pct = int(round(pct_norm * 100))
    # MIDI 0 (%0) -> 64 (%50) -> 127 (%100)
    cc_val = int(_clamp(round(pct_norm * 127), 0, 127))

    if x < 0:
        # Sol Yarı -> Deck 1 FX (B00B / FX1-1), Deck 2 (B00D / FX2-1) 0'da sabit
        return (cc_val, 0, pct, 0, 1)
    else:
        # Sağ Yarı -> Deck 2 FX (B00D / FX2-1), Deck 1 (B00B / FX1-1) 0'da sabit
        return (0, cc_val, 0, pct, 2)


def stick_to_midi(value: float, deadzone: float = STICK_DEADZONE) -> int:
    """Bipolar (-1.0..+1.0) analog çubuk değerini 0..127 MIDI CC aralığına ölçekler (merkez 64)."""
    v = _clamp(float(value), -1.0, 1.0)
    mag = abs(v)
    if mag <= deadzone:
        return STICK_CENTER
    norm = (mag - deadzone) / (1.0 - deadzone)
    if v < 0:
        out = STICK_CENTER - norm * STICK_CENTER
    else:
        out = STICK_CENTER + norm * (127 - STICK_CENTER)
    return int(_clamp(round(out), 0, 127))


def stick_y_to_midi(value: float, deadzone: float = STICK_Y_DEADZONE,
                    unipolar: bool | None = None) -> int:
    use_uni = Y_AXIS_UNIPOLAR if unipolar is None else unipolar
    if use_uni:
        v = _clamp(float(value), 0.0, 1.0)
        if v <= deadzone:
            return 0
        norm = (v - deadzone) / (1.0 - deadzone)
        return int(_clamp(round(norm * 127), 0, 127))
    return stick_to_midi(value, deadzone=deadzone)


def trigger_to_midi(value: float, deadzone: float = TRIGGER_DEADZONE) -> int:
    """Unipolar (0.0..+1.0) tetik değerini 0..127 MIDI CC aralığına ölçekler."""
    v = _clamp(float(value), 0.0, 1.0)
    if v <= deadzone:
        return 0
    norm = (v - deadzone) / (1.0 - deadzone)
    return int(_clamp(round(norm * 127), 0, 127))


def axis_to_midi(axis: AxisMap, value: float) -> int:
    if axis.invert:
        value = -value if axis.kind in ("stick", "stick_y") else 1.0 - value
    if axis.kind in ("cfx_deck1", "cfx_deck2", "stick"):
        return stick_to_midi(value)
    if axis.kind == "stick_y":
        return stick_y_to_midi(value)
    return trigger_to_midi(value)


# --------------------------------------------------------------------------- #
#  Rekordbox .midi.csv Üretici
# --------------------------------------------------------------------------- #
def _csv_row(
    name: str,
    ctrl_type: str,
    hex_code: str,
    *,
    deck: int = 0,
    midi_out: bool = True,
    option: str = "",
    comment: str = "",
) -> str:
    """
    Rekordbox 15 sütunlu .midi.csv satırı üretir:
      [0] name, [1] function, [2] type,
      [3] input (Deck '-'), [4] deck1, [5] deck2, [6] deck3, [7] deck4,
      [8] output (Deck '-'), [9] out_deck1, [10] out_deck2, [11] out_deck3, [12] out_deck4,
      [13] option, [14] comment
    ÖNEMLİ: Rekordbox'ta FX sekmesindeki tüm komutlar (CFX, FX1, ReleaseFX)
    global efekt ünitesi olduğu için `deck=0` (Rekordbox arayüzünde Deck: `-`)
    sütununa (Sütun 3) yazılmalıdır ve KnobSlider satırlarında MIDI OUT boş olmalıdır.
    """
    cols = [""] * 15
    cols[0] = name
    cols[2] = ctrl_type
    in_idx = 3 if deck == 0 else (3 + deck)
    cols[in_idx] = hex_code
    if midi_out and ctrl_type != "KnobSlider":
        out_idx = 8 if deck == 0 else (8 + deck)
        cols[out_idx] = hex_code
    cols[13] = option
    cols[14] = comment
    return ",".join(cols)


def build_rekordbox_csv(device_name: str = VIRTUAL_PORT_NAME) -> str:
    """
    Rekordbox 6 & 7 ile %100 uyumlu (CRLF satır sonlu) .midi.csv içeriği üretir.
    DDJ-FLX4 standardına birebir uygun olarak:
      * CFX ve FX komutları -> Sütun 3 (Deck: `-`) ve KnobSlider için MIDI OUT boş (`Fast`)
      * PAD ve MIXER komutları -> Sütun 4 (Deck: `1`)
    """
    btn_opt = "Fast;Blink=1000;Priority=50;"
    lines = [
        f"@file,1,{device_name}",
        # --- ADIM 1: XDJ-AZ SOUND COLOR FX (CFX - Deck: `-`) ---
        # Sol Analog Sol Yarı (B00A) -> Deck 1 CFX Knob, Sağ Yarı (B00C) -> Deck 2 CFX Knob
        _csv_row("CFXParameterCH1", "KnobSlider", "B00A", deck=0, midi_out=False, option="Fast", comment="Deck 1 CFX Knob (Sol Analog Sol Yari)"),
        _csv_row("CFXParameterCH2", "KnobSlider", "B00C", deck=0, midi_out=False, option="Fast", comment="Deck 2 CFX Knob (Sol Analog Sag Yari)"),
        # LB (Dub Echo) ve RB (Noise) için CFX On + CFX Select Next / Back
        _csv_row("CFXOn", "Button", "9048", deck=0, option=btn_opt, comment="CFX On/Off (LB Dub Echo / RB Noise)"),
        _csv_row("CFXSelect", "Button", "904A", deck=0, option=btn_opt, comment="CFX Select Next (Asagi -> LB Dub Echo)"),
        _csv_row("CFXSelectBack", "Button", "904B", deck=0, option=btn_opt, comment="CFX Select Back (Yukari -> RB Noise)"),
        # --- BEAT FX (Deck: `-`) ---
        # Sağ Analog Sol Yarı (B00B) -> Deck 1 FX LevelDepth, Sağ Yarı (B00D) -> Deck 2 FX LevelDepth
        _csv_row("FX1-1", "KnobSlider", "B00B", deck=0, midi_out=False, option="Fast", comment="Deck 1 Beat FX Depth (Sag Analog Sol Yari)"),
        _csv_row("FX2-1", "KnobSlider", "B00D", deck=0, midi_out=False, option="Fast", comment="Deck 2 Beat FX Depth (Sag Analog Sag Yari)"),
        # Menu Tuşu (9047) -> Beat FX On/Off Toggle
        _csv_row("FX1-1On", "Button", "9047", deck=0, option=btn_opt, comment="Menu Tusu / FX1-1 On (Toggle)"),
        _csv_row("FX2-1On", "Button", "904D", deck=0, option=btn_opt, comment="Menu Tusu / FX2-1 On (Toggle)"),
        # --- Stems (Deck 1): D-Pad Yukarı (Vocal), Sol (Inst), Aşağı (Drums), View (Mute/Solo) ---
        _csv_row("ActivePartVocal", "DdjSxPad", "9042", deck=1, comment="Stems Vocal (Deck 1)"),
        _csv_row("ActivePartInst", "DdjSxPad", "9044", deck=1, comment="Stems Inst (Deck 1)"),
        _csv_row("ActivePartDrums", "DdjSxPad", "9043", deck=1, comment="Stems Drums (Deck 1)"),
        _csv_row("ActivePartMuteSolo", "Button", "9049", deck=0, option=btn_opt, comment="Stems Mute/Solo"),
        # --- Pad FX 1 (Deck 1): A (Pad 1), B (Pad 2), X (Pad 3), Y (Pad 4) ---
        _csv_row("PAD1_PadFx1", "DdjSxPad", "903C", deck=1, comment="PadFX 1 (1/4 Roll)"),
        _csv_row("PAD2_PadFx1", "DdjSxPad", "903D", deck=1, comment="PadFX 2 (1/2 Roll)"),
        _csv_row("PAD3_PadFx1", "DdjSxPad", "903E", deck=1, comment="PadFX 3 (Reverb Freeze)"),
        _csv_row("PAD4_PadFx1", "DdjSxPad", "903F", deck=1, comment="PadFX 4 (Spiral/Trans)"),
        # --- Tetikler (Deck: `-`) ---

        "",
    ]
    return "\r\n".join(lines)
