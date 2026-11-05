# 🎮 Xbox2MIDI DJ

**A turnkey macOS CoreMIDI virtual bridge turning an Xbox Wireless Controller into a high-performance companion DJ controller for Pioneer Rekordbox.**

Designed to sit right alongside hardware like the **Pioneer DDJ-FLX4**, **DDJ-400**, or any modular DJ setup, giving you ergonomic, tactile thumbstick control over **Dual-Deck Sound Color FX (CFX)**, **Dual-Deck Beat FX**, **Stems isolation**, and **Pad FX**.

---

## 📸 Overview & Architecture

```
┌─────────────────────────┐
│ Xbox Wireless Controller│ (Bluetooth / USB-C)
└────────────┬────────────┘
             │ macOS GameController.framework / HID
             ▼
┌─────────────────────────┐
│     Xbox2MIDI DJ App    │ (PySide6 GUI + PyInstaller .app)
│  - Radial Analog Split  │
│  - Deadzone & Angle Math│
│  - Sniper MIDI Learn    │
└────────────┬────────────┘
             │ Native CoreMIDI Virtual Port ("Xbox DJ Port")
             ▼
┌─────────────────────────┐
│    Pioneer Rekordbox    │ (Rekordbox 6 / 7 MIDI In)
│  - CFX (Dub Echo/Noise) │
│  - Beat FX Level/Depth  │
│  - Stems (Vocal/Drums)  │
└─────────────────────────┘
```

---

## ✨ Key Features

### 🎛️ Dual-Deck Sound Color FX (Left Analog Stick)
- **Split-Deck Joystick**:
  - **Left Half**: Controls **Deck 1 Sound Color FX** (`B00A` / CC 10).
  - **Right Half**: Controls **Deck 2 Sound Color FX** (`B00C` / CC 12).
- **Proportional Radial Scaling**:
  - Pull down (0°) = **0% (Neutral Center 64)**
  - Tilt 90° sideways = **50% Filter (CC 96)**
  - Push top corner = **100% Filter (CC 127)**
  - Letting go smoothly springs back to neutral **64** with deadzone rejection (`±0.08`).
- **CFX Hold Lock (L3 / Left Stick Click)**: Click the stick to lock and freeze the current filter value in place even after your thumb leaves the analog stick. Click again to unlock.

### ⚡ Instant CFX Select (LB & RB Bumpers)
- **LB (Left Bumper)**: Selects **DUB ECHO** (sends 3 fast `CFXSelect` pulses to jump directly to Dub Echo).
- **RB (Right Bumper)**: Selects **NOISE** (sends 3 fast `CFXSelectBack` pulses to jump directly to Noise).
- Built specifically around Rekordbox 7's CFX hierarchy:
  `[1] FILTER` ➔ `[2] JET` ➔ `[3] CRUSH` ➔ `[4] NOISE` ➔ `[5] PITCH` ➔ `[6] SPACE` ➔ `[7] DUB ECHO` ➔ `[8] SWEEP` ➔ `[9] GATE COMP`.

### 🌊 Dual-Deck Beat FX Level/Depth (Right Analog Stick)
- **Left Half**: Controls **Deck 1 Beat FX Level/Depth** (`B00B` / CC 11).
- **Right Half**: Controls **Deck 2 Beat FX Level/Depth** (`B00D` / CC 13).
- Scaled from 0% (0) to 100% (127).
- **FX Hold Lock (R3 / Right Stick Click)**: Freeze the current Beat FX wet/dry level at will.

### 🔘 Beat FX Switch (Menu / ≡ Button)
- Toggle Beat FX on/off instantly (`9047` / `FX1-1 On` & `904D` / `FX2-1 On`) on demand.

### 🎙️ Stems Control (D-Pad)
- **D-Pad Up (↑)**: Vocal Stem Mute / Solo (`9042`)
- **D-Pad Down (↓)**: Drums / Rhythm Stem Mute / Solo (`9043`)
- **D-Pad Left (←)**: Instrumental Stem Mute / Solo (`9044`)
- **D-Pad Right (→)**: **Smart Stems Reset** (`9045`) — tracks previously muted parts and restores full audio with a single click.
- **View / ⧉ Button**: Stems Waveform View Toggle (`9049`).

### 🥁 Pad FX 1–4 (ABXY Buttons)
- **A**: Pad FX 1 (`903C` — e.g. 1/4 Roll / Stutter)
- **B**: Pad FX 2 (`903D` — e.g. 1/2 Roll)
- **X**: Pad FX 3 (`903E` — e.g. Reverb Freeze)
- **Y**: Pad FX 4 (`903F` — e.g. Spiral / Trans)
- Supports selectable **Momentary (Hold)** or **Toggle** trigger modes.

### 🎯 Sniper MIDI Learn Mode
Eliminates joystick jitter during Rekordbox setup:
1. Click **`[🎯 Rekordbox MIDI Learn]`** on the GUI toolbar.
2. In Rekordbox MIDI settings, click **LEARN** on any target command.
3. Click the corresponding button on the Xbox2MIDI dashboard dictionary. An isolated, clean MIDI message is pulsed into Rekordbox with 100% accuracy.

---

## 🕹️ Complete MIDI Mapping Matrix (Channel 1)

| Xbox Control | Type | Hex / MIDI Code | Rekordbox Target Function | Description |
|---|---|---|---|---|
| **Left Stick (Left)** | Axis | CC 10 (`B00A`) | `CFX ParameterCH1` (Deck: `-`) | Deck 1 Sound Color FX Depth |
| **Left Stick (Right)** | Axis | CC 12 (`B00C`) | `CFX ParameterCH2` (Deck: `-`) | Deck 2 Sound Color FX Depth |
| **L3 (Left Stick Click)** | Button | Internal | `CFX Hold Lock` | Freezes current Deck 1 / 2 CFX value |
| **LB (Left Bumper)** | Button | Note 74 (`904A` x3) | `CFX Select Next` | Jumps CFX slot to **DUB ECHO** |
| **RB (Right Bumper)** | Button | Note 75 (`904B` x3) | `CFX Select Back` | Jumps CFX slot to **NOISE** |
| **Right Stick (Left)** | Axis | CC 11 (`B00B`) | `FX1-1 LevelDepth` (Deck: `-`) | Deck 1 Beat FX Wet/Dry Depth |
| **Right Stick (Right)** | Axis | CC 13 (`B00D`) | `FX2-1 LevelDepth` (Deck: `-`) | Deck 2 Beat FX Wet/Dry Depth |
| **R3 (Right Stick Click)**| Button | Internal | `FX Hold Lock` | Freezes current FX Level/Depth |
| **Menu Button (≡)** | Button | Note 71 (`9047`) / 77 (`904D`) | `FX1-1 On` / `FX2-1 On` | Beat FX Master On/Off Toggle |
| **D-Pad Up (↑)** | Button | Note 66 (`9042`) | `ActivePartVocal` (Deck: `1`) | Stems: Vocal Mute/Active |
| **D-Pad Down (↓)** | Button | Note 67 (`9043`) | `ActivePartDrums` (Deck: `1`) | Stems: Drums Mute/Active |
| **D-Pad Left (←)** | Button | Note 68 (`9044`) | `ActivePartInst` (Deck: `1`) | Stems: Instrumental Mute/Active |
| **D-Pad Right (→)** | Button | Note 69 (`9045`) | `ActivePartReset` (Deck: `1`) | Stems: Reset all channels to full |
| **View Button (⧉)** | Button | Note 73 (`9049`) | `ActivePartDetail` (Deck: `1`) | Stems: Toggle waveform view |
| **A Button** | Button | Note 60 (`903C`) | `PAD1_PadFx1` (Deck: `1`) | Pad FX 1 (1/4 Roll) |
| **B Button** | Button | Note 61 (`903D`) | `PAD2_PadFx1` (Deck: `1`) | Pad FX 2 (1/2 Roll) |
| **X Button** | Button | Note 62 (`903E`) | `PAD3_PadFx1` (Deck: `1`) | Pad FX 3 (Reverb Freeze) |
| **Y Button** | Button | Note 63 (`903F`) | `PAD4_PadFx1` (Deck: `1`) | Pad FX 4 (Spiral) |

---

## 🚀 Quick Start Guide

### 1. Connect Controller
Pair your Xbox Wireless Controller to your Mac via Bluetooth (**System Settings ➔ Bluetooth**) or connect it using a USB-C cable.

### 2. Launch the Application
- Download or open **`dist/Xbox2MIDI DJ.app`** (or double-click **`run.command`**).
- On startup, the app automatically copies the latest pre-configured MIDI mapping (`Xbox_DJ_Port.midi.csv`) into:
  ```
  ~/Library/Application Support/Pioneer/rekordbox6/MidiMappings/
  ```
- Click **▶ KÖPRÜYÜ BAŞLAT (Start Bridge)**.

### 3. Configure Rekordbox
1. Open **Rekordbox**.
2. Click the **MIDI** button in the upper toolbar (next to *Preferences*).
3. In the device dropdown, select **Xbox DJ Port** (or **IAC Sürücüsü Yol 1**).
4. If not automatically loaded, click **IMPORT** and select **`Xbox_DJ_Port.midi.csv`** from this project directory.
5. You're ready to perform!

---

## 🛠️ Development & Building from Source

### Prerequisites
- macOS 12.0+ (Apple Silicon or Intel)
- Python 3.10+

### Setup Environment
```bash
# Clone the repository
git clone https://github.com/USERNAME/xbox2midi-dj.git
cd xbox2midi-dj

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run Locally
```bash
python3 main.py
```

### Build Standalone macOS App Bundle
```bash
./build_app.command
```
The compiled application will be generated in `dist/Xbox2MIDI DJ.app`.

---

## 📄 License
MIT License. Feel free to use, modify, and integrate into your DJ sets!
