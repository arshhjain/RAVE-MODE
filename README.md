# Rave Mode 2.0 🎵✨

> **Turn your room into a living, breathing extension of your sound.**  
> A real-time, zero-latency system audio visualizer that drives physical WLED strips directly from system loopback audio—no plugins, virtual audio cables, or middlemen required.

[![Demo Videos](https://img.shields.io/badge/Demo-Google_Drive-blue?logo=google-drive)](https://drive.google.com/drive/folders/1nj2Y85VmDmHyBLojrzciqGqGfaEA986O?usp=sharing)
[![Platform](https://img.shields.io/badge/Platform-Windows_10%2F11-0078D6?logo=windows)](https://microsoft.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![WLED](https://img.shields.io/badge/Hardware-WLED_UDP-FF6F00)](https://kno.wled.ge/)

---

## ⚡ What’s New in v2.0

Version 2.0 is a complete ground-up rebuild engineered to adapt seamlessly across genres, improve color fidelity, and bring the ambient physical experience directly onto your desktop.

### 🪟 A UI That Breathes
The old static visualizer and pulsating blobs are gone. The UI now runs a synchronized, high-framerate ambient light engine that mirrors your physical LED strip in real time—interpolated directly from your album artwork palette.

### 📌 Always-on-Top Miniplayer
A compact, distraction-free floating controller with full dynamic audio response. Pinned to the top of your workspace so you can keep the visuals alive without sacrificing desktop real estate.

### 🧠 Adaptive Mood Matching
The audio pipeline has been overhauled beyond simple peak detection. It continuously analyzes musical dynamics—swells, breakdowns, drops, and acoustic valleys—dynamically adjusting attack/decay envelopes and responsiveness on the fly. No more constant knob adjustments between ambient tracks and high-energy EDM.

### 🎯 Hardware Calibration & Precision Lighting
Consumer LED strips often skew warm or oversaturate mid-tones. v2.0 introduces a dedicated hardware calibration step to profile your specific strip's RGB profile, ensuring the colors hitting your walls match the true art intent.

---

## 🛠️ Architecture & Pipeline

```text
[System Audio Loopback] ──> (WASAPI / Soundcard)
│
▼
[Real-time FFT Engine]
(Bass / Treble Separation + Dynamics)
│
[Windows Media Session]           ▼
(Album Art Extraction) ──> [Color Engine] ──> [Hardware Calibration Curve]
│
┌─────────────────────┴─────────────────────┐
▼                                           ▼
[Local Web UI / Miniplayer]                 [UDP Socket @ 21324]
(Canvas API, Display P3 Gamut)                        │
▼
[WLED Strip Driver]
```

- **Zero-Cable Audio Loopback:** Hooks directly into Windows WASAPI loopback without routing virtual audio devices.
- **Dynamic FFT Pipeline:** Isolates spectral energy per frame using independent attack/decay curves and automatic gain control (AGC).
- **Quantized Color Interpolation:** Extracts a 3-color palette from active track artwork using Pillow and transitions smoothly via linear interpolation (LERP) without harsh snaps.
- **Direct UDP Broadcast:** Pushes sub-millisecond Gaussian light packets directly over local WiFi/Ethernet to any WLED-compatible ESP8266/ESP32 controller.

---

## 🚀 Getting Started

### Prerequisites
- **OS:** Windows 10 / 11 (requires WASAPI & WinRT Media Session support)
- **Python:** 3.10 or later
- **Hardware:** Any addressable LED strip (WS2812B, SK6812, etc.) running [WLED](https://kno.wled.ge/) on your local network

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/arshhjain/RAVE-MODE.git
   cd RAVE-MODE
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Launch Rave Mode:**
   ```bash
   python main.py
   ```

4. **Connect your hardware:**
   * Open the **Settings** panel in the app.
   * Enter your WLED controller's **Local IP Address** and **LED count**.
   * Run the initial **Hardware Calibration** sequence to tune strip color fidelity.
   * Start playing music on Spotify, Tidal, YouTube, or your browser.

> **Note:** The UI runs on `http://localhost:7373`. If you close the main desktop window or minimize it to the system tray, you can access the dashboard from any browser on your local network.

---

## 🎛️ Real-Time Parameters

All settings sync dynamically over WebSockets and automatically persist to `vibesync_config.json`:

| Parameter | Function | Behavior |
| --- | --- | --- |
| **Sensitivity** | Master reactivity | Scales audio input threshold |
| **Brightness** | Ambient base level | Minimum resting luminosity |
| **Saturation** | Color vibrancy | Adjusts vividness of extracted album palette |
| **Responsiveness** | Envelope curve | Toggles between floaty, ambient swell and snappy transients |
| **Bass / Treble Drive** | Frequency weighting | Individual gain multipliers per band |
| **Bass / Treble Width** | Spatial dispersion | Center bloom spread vs. outer edge flash length |
| **Treble Zone** | Spatial origin | Defines inward reach of high-frequency pulses |
| **Hardware Trim** | Color balance | Profiles R/G/B balance for specific LED chipsets |

---

## 🗂️ Project Structure

```text
rave-mode/
├── main.py              # Audio capture engine, palette extractor, entry point
├── state.py             # Global state engine, WebSocket sync, config persistence
├── requirements.txt     # Python dependencies
└── ui/
    ├── index.html       # Frameless dashboard & canvas visualizer
    └── static/          # WebSocket controllers, style definitions
```

---

## 🧰 Tech Stack

| Domain | Technology |
| --- | --- |
| **Audio Capture** | `soundcard` (Windows WASAPI loopback) |
| **Signal Processing** | `numpy` (Fast Fourier Transform, energy isolation) |
| **Media Metadata** | `winsdk` (Windows Media Session API) |
| **Color Processing** | `Pillow` (Palette quantization, Gaussian blur) |
| **Networking & API** | `FastAPI`, `uvicorn`, native UDP sockets |
| **Frontend Shell** | `pywebview` (Frameless native container), Vanilla JS, Canvas API |
| **Background Service** | `pystray` (System tray management) |

---

## 💡 Use Cases & Roadmap

* [x] Living room / desk ambient reactive backlighting
* [ ] Multi-segment zoning for large rooms / separate LED channels
* [ ] Car infotainment integration via secondary mini-display rigs
* [ ] DMX / Stage venue protocol output bridge

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
