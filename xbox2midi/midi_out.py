"""
Xbox2MIDI DJ - Yerel CoreMIDI çıkışı (ctypes, sıfır derleme bağımlılığı).

İki çıkış modu desteklenir:
  1. Sanal kaynak  : Sistemde "Xbox DJ Port" adında yeni bir CoreMIDI cihazı
                     yayınlar. Rekordbox bunu doğrudan bir MIDI girişi olarak görür.
  2. Hedef (IAC)   : "IAC Driver Bus 1 / IAC Sürücüsü Yol 1" gibi mevcut bir
                     CoreMIDI hedefine mesaj gönderir.

python-rtmidi gibi C uzantısı gerektiren paketler kullanılmaz; böylece her
Python sürümünde (3.9 – 3.14) ve Apple Silicon'da derleme gerekmeden çalışır.
CoreMIDI fonksiyonları thread-safe'tir; worker thread'den güvenle çağrılabilir.
"""
from __future__ import annotations

import ctypes
import threading
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

from . import config

# --------------------------------------------------------------------------- #
#  Framework yükleme ve imzalar
# --------------------------------------------------------------------------- #
_CM = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI")
_CF = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

OSStatus = ctypes.c_int32
MIDIObjectRef = ctypes.c_uint32
ItemCount = ctypes.c_ulong
ByteCount = ctypes.c_ulong
MIDITimeStamp = ctypes.c_uint64
CFStringRef = ctypes.c_void_p

kCFStringEncodingUTF8 = 0x08000100
kMIDIIDNotUnique = -10843


def _fn(lib, name, restype, *argtypes):
    f = getattr(lib, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


CFStringCreateWithCString = _fn(_CF, "CFStringCreateWithCString", CFStringRef,
                                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32)
CFStringGetCString = _fn(_CF, "CFStringGetCString", ctypes.c_bool,
                         CFStringRef, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32)
CFRelease = _fn(_CF, "CFRelease", None, ctypes.c_void_p)

MIDIClientCreate = _fn(_CM, "MIDIClientCreate", OSStatus,
                       CFStringRef, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(MIDIObjectRef))
MIDIClientDispose = _fn(_CM, "MIDIClientDispose", OSStatus, MIDIObjectRef)
MIDISourceCreate = _fn(_CM, "MIDISourceCreate", OSStatus,
                       MIDIObjectRef, CFStringRef, ctypes.POINTER(MIDIObjectRef))
MIDIOutputPortCreate = _fn(_CM, "MIDIOutputPortCreate", OSStatus,
                           MIDIObjectRef, CFStringRef, ctypes.POINTER(MIDIObjectRef))
MIDIEndpointDispose = _fn(_CM, "MIDIEndpointDispose", OSStatus, MIDIObjectRef)
MIDIPortDispose = _fn(_CM, "MIDIPortDispose", OSStatus, MIDIObjectRef)
MIDIGetNumberOfDestinations = _fn(_CM, "MIDIGetNumberOfDestinations", ItemCount)
MIDIGetDestination = _fn(_CM, "MIDIGetDestination", MIDIObjectRef, ItemCount)
MIDIObjectGetStringProperty = _fn(_CM, "MIDIObjectGetStringProperty", OSStatus,
                                  MIDIObjectRef, CFStringRef, ctypes.POINTER(CFStringRef))
MIDIObjectGetIntegerProperty = _fn(_CM, "MIDIObjectGetIntegerProperty", OSStatus,
                                   MIDIObjectRef, CFStringRef, ctypes.POINTER(ctypes.c_int32))
MIDIObjectSetIntegerProperty = _fn(_CM, "MIDIObjectSetIntegerProperty", OSStatus,
                                   MIDIObjectRef, CFStringRef, ctypes.c_int32)
MIDIPacketListInit = _fn(_CM, "MIDIPacketListInit", ctypes.c_void_p, ctypes.c_void_p)
MIDIPacketListAdd = _fn(_CM, "MIDIPacketListAdd", ctypes.c_void_p,
                        ctypes.c_void_p, ByteCount, ctypes.c_void_p,
                        MIDITimeStamp, ByteCount, ctypes.c_char_p)
MIDIReceived = _fn(_CM, "MIDIReceived", OSStatus, MIDIObjectRef, ctypes.c_void_p)
MIDISend = _fn(_CM, "MIDISend", OSStatus, MIDIObjectRef, MIDIObjectRef, ctypes.c_void_p)


def _const_key(text: str) -> int:
    # CoreMIDI'nin dışa aktardığı kMIDIProperty* sabitleri, framework tembel
    # (lazy) başlatıldığı için içe aktarma anında NULL olabilir. Anahtarlar
    # string eşitliğiyle karşılaştırıldığından belgelenmiş değerleriyle
    # kalıcı CFString'ler oluşturmak güvenli ve deterministiktir.
    ref = CFStringCreateWithCString(None, text.encode("utf-8"), kCFStringEncodingUTF8)
    if not ref:
        raise RuntimeError(f"CFString oluşturulamadı: {text}")
    return ref  # Uygulama ömrü boyunca tutulur (bilinçli olarak serbest bırakılmaz)


kMIDIPropertyDisplayName = _const_key("displayName")
kMIDIPropertyUniqueID = _const_key("uniqueID")
kMIDIPropertyOffline = _const_key("offline")


# --------------------------------------------------------------------------- #
#  Yardımcılar
# --------------------------------------------------------------------------- #
class MidiError(RuntimeError):
    pass


def _cfstr(text: str) -> int:
    ref = CFStringCreateWithCString(None, text.encode("utf-8"), kCFStringEncodingUTF8)
    if not ref:
        raise MidiError(f"CFString oluşturulamadı: {text!r}")
    return ref


def _pystr(ref: int) -> str:
    buf = ctypes.create_string_buffer(512)
    ok = CFStringGetCString(ref, buf, len(buf), kCFStringEncodingUTF8)
    return buf.value.decode("utf-8", "replace") if ok else ""


def _check(status: int, what: str) -> None:
    if status != 0:
        raise MidiError(f"{what} başarısız (OSStatus {status})")


def _get_str_prop(obj: int, prop: int) -> str:
    out = CFStringRef()
    if MIDIObjectGetStringProperty(obj, prop, ctypes.byref(out)) != 0 or not out.value:
        return ""
    try:
        return _pystr(out.value)
    finally:
        CFRelease(out.value)


def _get_int_prop(obj: int, prop: int, default: int = 0) -> int:
    out = ctypes.c_int32()
    if MIDIObjectGetIntegerProperty(obj, prop, ctypes.byref(out)) != 0:
        return default
    return out.value


@dataclass(frozen=True)
class Destination:
    unique_id: int
    name: str

    @property
    def is_iac(self) -> bool:
        n = self.name.lower()
        return "iac" in n


VIRTUAL_TARGET_ID = 0  # GUI'de "sanal port" seçeneğinin kimliği


def list_destinations() -> List[Destination]:
    """Sistemdeki çevrimiçi CoreMIDI hedeflerini listeler (IAC dahil)."""
    result: List[Destination] = []
    for i in range(MIDIGetNumberOfDestinations()):
        ep = MIDIGetDestination(i)
        if not ep or _get_int_prop(ep, kMIDIPropertyOffline, 0):
            continue
        name = _get_str_prop(ep, kMIDIPropertyDisplayName) or f"Hedef {i + 1}"
        uid = _get_int_prop(ep, kMIDIPropertyUniqueID, 0)
        if uid == VIRTUAL_TARGET_ID:
            continue
        result.append(Destination(uid, name))
    return result


def find_iac() -> Optional[Destination]:
    for d in list_destinations():
        if d.is_iac:
            return d
    return None


def _find_endpoint(unique_id: int) -> int:
    for i in range(MIDIGetNumberOfDestinations()):
        ep = MIDIGetDestination(i)
        if ep and _get_int_prop(ep, kMIDIPropertyUniqueID, 0) == unique_id:
            return ep
    return 0


# --------------------------------------------------------------------------- #
#  MIDI çıkışı
# --------------------------------------------------------------------------- #
class MidiOut:
    """
    Tek kanallı (Channel 1), MPE'siz CoreMIDI çıkışı.

    Bir uygulama ömrü boyunca tek bir CoreMIDI istemcisi tutulur; hedef
    (sanal port / IAC) çalışma anında değiştirilebilir.
    """

    _BUF_SIZE = 4096

    def __init__(self, client_name: str = config.APP_NAME) -> None:
        self._lock = threading.Lock()
        self._client = MIDIObjectRef()
        name = _cfstr(client_name)
        try:
            _check(MIDIClientCreate(name, None, None, ctypes.byref(self._client)), "MIDIClientCreate")
        finally:
            CFRelease(name)
        self._source = 0          # sanal kaynak endpoint
        self._out_port = 0        # IAC'a gönderim için çıkış portu
        self._dest = 0            # hedef endpoint
        self._target_label = ""
        self._buf = ctypes.create_string_buffer(self._BUF_SIZE)

    # ---- hedef yönetimi ------------------------------------------------- #
    @property
    def is_open(self) -> bool:
        return bool(self._source or (self._out_port and self._dest))

    @property
    def target_label(self) -> str:
        return self._target_label

    def open_virtual(self, name: str = config.VIRTUAL_PORT_NAME) -> str:
        with self._lock:
            self._close_locked()
            src = MIDIObjectRef()
            cf = _cfstr(name)
            try:
                _check(MIDISourceCreate(self._client, cf, ctypes.byref(src)), "MIDISourceCreate")
            finally:
                CFRelease(cf)
            # Sabit UniqueID: Rekordbox MIDI eşlemelerinin her açılışta korunması için.
            st = MIDIObjectSetIntegerProperty(src, kMIDIPropertyUniqueID, config.VIRTUAL_PORT_UNIQUE_ID)
            if st not in (0, kMIDIIDNotUnique):
                pass  # Kritik değil; CoreMIDI rastgele bir kimlik atar.
            self._source = src.value
            self._target_label = f"{name} (Sanal CoreMIDI)"
            return self._target_label

    def open_destination(self, unique_id: int) -> str:
        with self._lock:
            self._close_locked()
            ep = _find_endpoint(unique_id)
            if not ep:
                raise MidiError("Seçilen MIDI hedefi bulunamadı (çevrimdışı olabilir).")
            port = MIDIObjectRef()
            cf = _cfstr(f"{config.APP_NAME} Out")
            try:
                _check(MIDIOutputPortCreate(self._client, cf, ctypes.byref(port)), "MIDIOutputPortCreate")
            finally:
                CFRelease(cf)
            self._out_port = port.value
            self._dest = ep
            self._target_label = _get_str_prop(ep, kMIDIPropertyDisplayName) or "MIDI Hedefi"
            return self._target_label

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._source:
            MIDIEndpointDispose(self._source)
            self._source = 0
        if self._out_port:
            MIDIPortDispose(self._out_port)
            self._out_port = 0
        self._dest = 0
        self._target_label = ""

    def dispose(self) -> None:
        self.close()
        if self._client.value:
            MIDIClientDispose(self._client)
            self._client = MIDIObjectRef()

    # ---- gönderim -------------------------------------------------------- #
    def send(self, messages: Sequence[Sequence[int]]) -> None:
        """Bir karedeki tüm mesajları tek bir MIDIPacketList ile gönderir."""
        if not messages:
            return
        with self._lock:
            if not self.is_open:
                return
            buf = self._buf
            cur = MIDIPacketListInit(buf)
            for msg in messages:
                data = bytes(msg)
                cur = MIDIPacketListAdd(buf, self._BUF_SIZE, cur, 0, len(data), data)
                if not cur:
                    break
            if self._source:
                MIDIReceived(self._source, buf)
            else:
                MIDISend(self._out_port, self._dest, buf)


# --------------------------------------------------------------------------- #
#  Mesaj fabrikaları — kanal daima config.MIDI_CHANNEL (Channel 1)
# --------------------------------------------------------------------------- #
_CH = config.MIDI_CHANNEL & 0x0F


def cc(control: int, value: int) -> tuple:
    return (0xB0 | _CH, control & 0x7F, value & 0x7F)


def note_on(note: int, velocity: int = config.NOTE_ON_VELOCITY) -> tuple:
    return (0x90 | _CH, note & 0x7F, velocity & 0x7F)


def note_off(note: int) -> tuple:
    if config.NOTE_OFF_STYLE == "note_on_zero":
        return (0x90 | _CH, note & 0x7F, 0)
    return (0x80 | _CH, note & 0x7F, 0)


def describe(msgs: Iterable[Sequence[int]]) -> List[str]:
    out = []
    for status, d1, d2 in msgs:
        kind = status & 0xF0
        raw_hex = f"{status:02X} {d1:02X} {d2:02X}"
        if kind == 0xB0:
            ax = config.AXIS_BY_CC.get(d1)
            hex_in = f"B0{d1:02X}"
            if ax:
                out.append(
                    f"[MIDI IN: {hex_in}]  {ax.label:<16} → {ax.rekordbox_cmd:<32} · Değer: {d2:3d} (CC {d1:2d} | {raw_hex})"
                )
            else:
                out.append(f"[MIDI IN: {hex_in}]  CC {d1} · Değer: {d2} ({raw_hex})")
        elif kind == 0x90 and d2 > 0:
            btn = config.BUTTON_BY_NOTE.get(d1)
            hex_in = f"90{d1:02X}"
            if btn:
                out.append(
                    f"[MIDI IN: {hex_in}]  {btn.label:<18} → {btn.rekordbox_cmd:<32} · ON  (Note {d1} | {raw_hex})"
                )
            else:
                out.append(f"[MIDI IN: {hex_in}]  Note {d1} · ON  (vel {d2} | {raw_hex})")
        else:
            btn = config.BUTTON_BY_NOTE.get(d1)
            hex_in = f"90{d1:02X}"
            if btn:
                out.append(
                    f"[MIDI IN: {hex_in}]  {btn.label:<18} → {btn.rekordbox_cmd:<32} · OFF (Note {d1} | {raw_hex})"
                )
            else:
                out.append(f"[MIDI IN: {hex_in}]  Note {d1} · OFF ({raw_hex})")
    return out
