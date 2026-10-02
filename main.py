import asyncio, base64, colorsys, io, json, math, os, socket, time
import sys, threading, warnings, queue, urllib.request
from collections import deque

import numpy as np
import soundcard as sc
from PIL import Image, ImageFilter, ImageEnhance
from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager)
from winsdk.windows.storage.streams import DataReader

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

import webview
import pystray

from state import state

# ── paths ──────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE = sys._MEIPASS
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

UI_FILE = os.path.join(BASE, "ui", "index.html")

# ── audio constants ────────────────────────────────────────────────────
SAMPLE_RATE = 48000
CHUNK = 256
BASS_WINDOW = 1024
TREBLE_CUTOFF = 350
BASS_CUTOFF_HZ = 250
GAIN_WINDOW = 2.5
SILENCE_THRESHOLD = 0.002
SEND_HZ = 50  # network frame rate — decoupled from audio chunk rate

# Saturation multiplier applied to extracted album-art colors
EXTRACTION_SATURATION_BOOST = 1.0

VERSION = "2.2.0"
GITHUB_REPO = "arshhjain/RAVE-MODE"

def check_for_updates():
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={'User-Agent': 'RaveMode-Updater'})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            data = json.loads(response.read().decode())
            latest = data.get("tag_name", "").lstrip("v")
            if latest and latest != VERSION:
                state.update_url = data.get("html_url")
    except Exception as e:
        print(f"[updater] Check failed: {e}")

# ── helpers ────────────────────────────────────────────────────────────
def gaussian(x, mu, sig, amp):
    if sig == 0: return np.zeros_like(x)
    return amp * np.exp(-np.power(x - mu, 2.) / (2 * np.power(sig, 2.)))


def boost_saturation(rgb, factor):
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    if factor <= 1.0:
        s = s * max(0.0, factor)
    else:
        # Smooth asymptotic vibrance headroom: never hard-clips, distributes evenly across range
        s = min(1.0, s + (1.0 - s) * (factor - 1.0) * 0.85)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return [int(r * 255), int(g * 255), int(b * 255)]


def extract_color_candidates(image):
    """Heavy operation: quantizes image to extract dominant colors."""
    try:
        small = image.resize((48, 48), resample=Image.Resampling.NEAREST)
        paletted = small.quantize(colors=12, method=Image.Quantize.FASTOCTREE)
        dominant = paletted.getcolors()
        palette = paletted.getpalette()

        if not dominant or not palette:
            return []

        candidates = []
        for count, index in dominant:
            r, g, b = palette[index * 3: index * 3 + 3]
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            if v < 0.10: continue
            score = s * 0.6 + v * 0.3 + (count / 2304) * 2.5
            candidates.append(((r, g, b), (h, s, v), score))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return candidates
    except Exception as e:
        print(f"[color_extract] error: {e}")
        return []

def _clean_subpixels(rgb_color, threshold_ratio=0.06):
    """
    Zeroes out any subpixel that contributes less than a specific ratio to the max subpixel.
    This entirely prevents 0-to-1 threshold flicker on fading RGB LEDs.
    """
    max_val = max(rgb_color)
    if max_val == 0:
        return [0, 0, 0]
    return [c if (c / max_val) > threshold_ratio else 0 for c in rgb_color]

def resolve_palette(candidates, mode="cohesive", cone_level=2):
    """Lightweight mathematical resolution of a palette from a cached candidate list."""
    if not candidates:
        return [[30, 30, 60], [255, 255, 255], [0, 150, 255]]

    if mode == "cohesive":
        # Map cone_level to a cone width (max hue distance)
        if cone_level == 0: max_h_dist = 0.15      # Cozy
        elif cone_level == 1: max_h_dist = 0.25    # Lounge
        elif cone_level == 2: max_h_dist = 0.35    # Accurate
        else: max_h_dist = 0.50                    # Rave

        bass_rgb, bass_hsv, _ = candidates[0]
        
        treble_hsv = None
        for rgb, hsv, _ in candidates[1:]:
            h_dist = min(abs(bass_hsv[0] - hsv[0]), 1.0 - abs(bass_hsv[0] - hsv[0]))
            if 0.08 <= h_dist <= max_h_dist:
                treble_hsv = hsv
                break
        
        if not treble_hsv:
            new_h = (bass_hsv[0] + (max_h_dist / 2.0)) % 1.0
            treble_hsv = (new_h, bass_hsv[1], bass_hsv[2])
        
        bass_v = 1.0  # Maximize luminance for explosive audio reactions
        bass_s = max(0.4, bass_hsv[1])
        
        tr, tg, tb = colorsys.hsv_to_rgb(treble_hsv[0], bass_s, bass_v)
        treble_rgb = (int(tr*255), int(tg*255), int(tb*255))
        
        br, bg, bb = colorsys.hsv_to_rgb(bass_hsv[0], bass_s, bass_v)
        bass_rgb = (int(br*255), int(bg*255), int(bb*255))
        
        mid_h = (bass_hsv[0] + treble_hsv[0]) / 2.0
        if abs(bass_hsv[0] - treble_hsv[0]) > 0.5:
            mid_h = (mid_h + 0.5) % 1.0
            
        # Boost background brightness so cohesive mode doesn't feel too dim
        bg_r, bg_g, bg_b = colorsys.hsv_to_rgb(mid_h, 0.35, 0.40)
        bg_rgb = (int(bg_r*255), int(bg_g*255), int(bg_b*255))
        # Clean subpixels to prevent 0-1 flicker on fade-outs
        bass_rgb = _clean_subpixels(bass_rgb)
        treble_rgb = _clean_subpixels(treble_rgb)
        
        return [list(bg_rgb), list(bass_rgb), list(treble_rgb)]

    else:
        # Legacy Mode
        selected_rgb = []
        selected_hsv = []

        for rgb, hsv, _ in candidates:
            if not selected_hsv:
                selected_rgb.append(rgb)
                selected_hsv.append(hsv)
                continue

            if all(_is_visually_distinct(hsv, prev) for prev in selected_hsv):
                selected_rgb.append(rgb)
                selected_hsv.append(hsv)

            if len(selected_rgb) == 3:
                break

        if len(selected_rgb) == 1:
            selected_rgb.append(_generate_fallback_accent(selected_hsv[0], hue_shift=0.33))
            selected_rgb.append(_generate_fallback_accent(selected_hsv[0], hue_shift=0.66))
        elif len(selected_rgb) == 2:
            selected_rgb.append(_generate_fallback_accent(selected_hsv[0], hue_shift=0.50))

        col_primary = _clean_subpixels(boost_saturation(selected_rgb[0], EXTRACTION_SATURATION_BOOST))
        col_accent = _clean_subpixels(boost_saturation(selected_rgb[2], EXTRACTION_SATURATION_BOOST))
        col_background = _clamp_background_brightness(selected_rgb[1])

        return [list(col_background), list(col_primary), list(col_accent)]

def get_top_3_colors(image, mode="cohesive", cone_level=2):
    """Wrapper function for backward compatibility."""
    candidates = extract_color_candidates(image)
    return resolve_palette(candidates, mode, cone_level)


def _clamp_background_brightness(rgb, min_v=0.18, max_v=0.42, target_s=0.15):
    """Keeps the background color from being pitch black (which makes the
    bass/treble blobs look chaotic against it) or too bright (which washes
    out the foreground accents). Limits artificial saturation boosts."""
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    v = max(min_v, min(max_v, v))
    s = max(s, target_s)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return [int(r * 255), int(g * 255), int(b * 255)]


def _is_visually_distinct(hsv1, hsv2, min_hue_diff=0.08, min_val_diff=0.25):
    """Checks circular hue distance (0.0-1.0) and contrast."""
    h_dist = min(abs(hsv1[0] - hsv2[0]), 1.0 - abs(hsv1[0] - hsv2[0]))
    s_dist = abs(hsv1[1] - hsv2[1])
    v_dist = abs(hsv1[2] - hsv2[2])
    return (h_dist >= min_hue_diff) or (v_dist >= min_val_diff and s_dist >= 0.15)


def _generate_fallback_accent(base_hsv, hue_shift=0.33):
    h, s, v = base_hsv
    new_h = (h + hue_shift) % 1.0
    new_s = max(0.35, s)
    new_v = max(0.6, v)
    r, g, b = colorsys.hsv_to_rgb(new_h, new_s, new_v)
    return [int(r * 255), int(g * 255), int(b * 255)]


def image_to_b64(img: Image.Image, quality: int = 90) -> str:
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode()


def get_stable_background_color(c1, brightness):
    """Computes pre-gamma background channel values that guarantee WS2812
    hardware stability (minimum ~4.5 PWM on dominant channel, ~1.8 PWM turn-on
    floor on active secondary channels) without collapsing into 8-bit black crush
    or 1-bit temporal dither chatter."""
    if brightness <= 0.005:
        return [0.0, 0.0, 0.0]

    # Map user brightness knob (0.01 to 1.0) into physical post-gamma PWM:
    # 4.5 PWM is the stable mixed-color hardware ignition floor for WS2812
    min_pwm = 4.5
    max_pwm = 38.0
    b_norm = max(0.0, min(1.0, (brightness - 0.005) / 0.995))
    target_pwm = min_pwm + (max_pwm - min_pwm) * (b_norm ** 1.15)

    max_c = max(c1[0], c1[1], c1[2], 1.0)
    bg_pre = [0.0, 0.0, 0.0]
    for i in range(3):
        rel = c1[i] / max_c
        if rel > 0.03:
            # Maintain color ratio while guarding against sub-turn-on dropout
            ch_pwm = max(1.8, target_pwm * rel)
            # Invert gamma 2.0: pre_val = sqrt(ch_pwm * 255.0)
            bg_pre[i] = math.sqrt(ch_pwm * 255.0)
        else:
            bg_pre[i] = 0.0

    return bg_pre


# ── per-segment rendering ──────────────────────────────────────────────
def render_segment(start, end, b_amp, t_amp, bw, tw, treble_zone,
                    bg_col, c2, c3, include_treble, r_out, g_out, b_out):
    """Render one segment's r/g/b arrays in-place to avoid GC thrashing."""
    seg_len = end - start
    x = np.arange(seg_len)
    bsh = gaussian(x, seg_len / 2.0, bw, b_amp)

    if include_treble:
        tz = min(treble_zone, max(1.0, seg_len / 2.0 - 1))
        tsh = gaussian(x, tz, tw, t_amp) + gaussian(x, seg_len - tz, tw, t_amp)
    else:
        tsh = np.zeros(seg_len)

    bg_fac = 1.0 - np.clip(bsh + tsh, 0, 1) * 0.9

    r_out[start:end] = bg_col[0] * bg_fac + bsh * c2[0] + tsh * c3[0]
    g_out[start:end] = bg_col[1] * bg_fac + bsh * c2[1] + tsh * c3[1]
    b_out[start:end] = bg_col[2] * bg_fac + bsh * c2[2] + tsh * c3[2]


def render_frame(n, b_amp, t_amp, bw, tw, treble_zone, bg_col, c2, c3, r_out, g_out, b_out):
    """Builds full-strip r/g/b arrays dynamically into pre-allocated out buffers."""
    mode = getattr(state, "segment_mode", "independent")
    segments = getattr(state, "segments", [[0, n]])
    if not segments:
        segments = [[0, n]]

    if mode == "continuous":
        x = np.arange(n)
        bsh = gaussian(x, n / 2.0, bw, b_amp)
        tsh = (gaussian(x, treble_zone, tw, t_amp)
               + gaussian(x, n - treble_zone, tw, t_amp))
        bg_fac = 1.0 - np.clip(bsh + tsh, 0, 1) * 0.9
        r_out[:] = bg_col[0] * bg_fac + bsh * c2[0] + tsh * c3[0]
        g_out[:] = bg_col[1] * bg_fac + bsh * c2[1] + tsh * c3[1]
        b_out[:] = bg_col[2] * bg_fac + bsh * c2[2] + tsh * c3[2]
        return

    r_out.fill(0)
    g_out.fill(0)
    b_out.fill(0)

    include_local_treble = mode == "independent"
    for seg in segments:
        if len(seg) < 2:
            continue
        start, end = int(seg[0]), int(seg[1])
        start = max(0, min(start, n))
        end = max(0, min(end, n))
        if start >= end:
            continue
        render_segment(
            start, end, b_amp, t_amp, bw, tw, treble_zone,
            bg_col, c2, c3, include_local_treble,
            r_out, g_out, b_out
        )

    if mode == "overlay":
        x = np.arange(n)
        tsh = (gaussian(x, treble_zone, tw, t_amp)
               + gaussian(x, n - treble_zone, tw, t_amp))
        r_out += tsh * c3[0]
        g_out += tsh * c3[1]
        b_out += tsh * c3[2]


# ── WLED client ────────────────────────────────────────────────────────
class WLEDClient:
    def __init__(self):
        self.sock = None
        self._init_socket()
        self.errors = np.zeros((2000, 3))
        self._last_err_time = 0.0
        self._queue = queue.Queue(maxsize=2)
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()

    def _sender_loop(self):
        while True:
            try:
                r, g, b = self._queue.get()
                self._send_pixels_internal(r, g, b)
            except Exception:
                pass

    def send_pixels(self, r, g, b):
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
        self._queue.put((r, g, b))

    def _init_socket(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        except Exception:
            pass

    def _send_pixels_internal(self, r, g, b):
        n = len(r)
        # 1. Perceptual gamma 2.0 correction (CIE lightness curve)
        # Cushions low-level jumps so near-off to bright transitions bloom smoothly
        rn = np.clip(r / 255.0, 0.0, 1.0)
        gn = np.clip(g / 255.0, 0.0, 1.0)
        bn = np.clip(b / 255.0, 0.0, 1.0)
        rg = (rn ** 2.0) * 255.0
        gg = (gn ** 2.0) * 255.0
        bg = (bn ** 2.0) * 255.0

        es = self.errors[:n]
        rd = rg + es[:, 0]
        gd = gg + es[:, 1]
        bd = bg + es[:, 2]

        ro = np.clip(rd, 0, 255).astype(np.uint8)
        go = np.clip(gd, 0, 255).astype(np.uint8)
        bo = np.clip(bd, 0, 255).astype(np.uint8)

        # 2. Dither noise-gate & stabilization:
        # Below 1.2 PWM, damp residual error to 0 so LEDs hold a clean dark baseline
        # instead of chattering / crawling between 0 and 1 at 25-50Hz.
        err_r = rd - ro
        err_g = gd - go
        err_b = bd - bo
        self.errors[:n, 0] = np.where(rg > 1.2, err_r * 0.85, 0.0)
        self.errors[:n, 1] = np.where(gg > 1.2, err_g * 0.85, 0.0)
        self.errors[:n, 2] = np.where(bg > 1.2, err_b * 0.85, 0.0)

        pix = np.dstack((ro, go, bo)).flatten().tobytes()
        try:
            self.sock.sendto(bytearray([2, 2]) + pix, (state.wled_ip, int(state.wled_port)))
        except OSError as e:
            now = time.monotonic()
            if now - self._last_err_time > 3.0:
                print(f"[wled] socket warning: {e}")
                self._last_err_time = now
            if getattr(e, 'winerror', None) in (10055, 10022, 10054) or "buffer" in str(e).lower():
                self._init_socket()
        except Exception as e:
            now = time.monotonic()
            if now - self._last_err_time > 3.0:
                print(f"[wled] {e}")
                self._last_err_time = now

    def clear_dither(self, n):
        self.errors[:n] = 0


def soft_limit(amp, target_max=0.95):
    """Compresses peaks smoothly so heavy sustained sub-bass or treble
    flashes never clip into flat solid blobs."""
    if amp <= 0:
        return 0.0
    return float(target_max * np.tanh(amp / target_max))


class AutoGain:
    def __init__(self):
        self.history = deque(maxlen=int((SAMPLE_RATE / CHUNK) * GAIN_WINDOW))
        self.current = 1.0
        self.track_change_time = 0.0
        self.gradient_duration = 4.0

    def on_track_change(self):
        """Flushes quiet baseline history and arms a 4.0s lead-in ease-in gradient."""
        self.history.clear()
        self.current = 0.85
        self.track_change_time = time.monotonic()

    def update(self, vol, mode="legacy"):
        self.history.append(vol)
        if not self.history:
            return 1.0
        # Track 92nd percentile peak to adapt sensitivity to sustained loud sections
        peak = float(np.percentile(self.history, 92))

        # 1. Silence gate: if the music drops to dead air / quiet silence between tracks,
        # anchor target gain near nominal 1.0 instead of violently pumping up to 6.0x.
        if peak < 0.012:
            target_gain = 1.0
        else:
            target_gain = max(0.20, min(3.5, 0.12 / (peak + 0.001)))
            
        # Overcompensate AGC volume for Cohesive mode because colors are lower contrast
        if mode == "cohesive":
            target_gain = min(5.0, target_gain * 1.6)

        # Fast attack when loud volume surge occurs (prevent redlining instantly),
        # slow release when music drops (prevent gain pumping)
        rate = 0.12 if target_gain < self.current else 0.015
        self.current += (target_gain - self.current) * rate

        out_gain = self.current

        # 2. Track-change lead-in gradient:
        # Prevent the first beat of a new track from clipping through AGC after a quiet intro/pause.
        if self.track_change_time > 0:
            elapsed = time.monotonic() - self.track_change_time
            if elapsed < self.gradient_duration:
                # S-curve smoothstep progress from 0.0 to 1.0
                p = max(0.0, min(1.0, elapsed / self.gradient_duration))
                smooth = p * p * (3.0 - 2.0 * p)

                # Dynamic ceiling prevents massive sudden spikes during the first seconds
                max_ceiling = 0.95 + 1.5 * smooth
                out_gain = min(out_gain, max_ceiling)

                # Easing multiplier: smooth ramp from 65% to 100%
                gradient = 0.65 + 0.35 * smooth
                out_gain *= gradient
            else:
                self.track_change_time = 0.0

        return out_gain


# ── audio thread ───────────────────────────────────────────────────────
def audio_listener(client: WLEDClient):
    warnings.filterwarnings("ignore")
    ff = np.fft.rfftfreq(CHUNK, 1.0 / SAMPLE_RATE)
    fs = np.fft.rfftfreq(BASS_WINDOW, 1.0 / SAMPLE_RATE)

    # ── Precompute Frequency Weight Curves ──
    # Bass weights: 1.5x at ~50Hz, 1.2x at ~120Hz, rolling off towards 250Hz.
    b_idx = np.where(fs < BASS_CUTOFF_HZ)[0]
    bass_weights = 0.5 + 1.0 * np.exp(-((fs[b_idx] - 50.0) ** 2) / (2 * 60.0 ** 2))

    # Treble weights: 0.8x in lower treble, scaling up to 1.4x higher up
    t_idx = np.where(ff > TREBLE_CUTOFF)[0]
    treble_weights = 0.8 + 0.6 * np.clip((ff[t_idx] - 2000.0) / 8000.0, 0, 1.0)

    while state.running:
        try:
            spk = sc.default_speaker()
            mic = sc.get_microphone(id=str(spk.name), include_loopback=True)
        except Exception as e:
            print(f"[audio] device open failed, retry in 2s: {e}")
            threading.Event().wait(2);
            continue

        bass_buf = np.zeros(BASS_WINDOW)
        agc = AutoGain()
        bv = tv = 0.0
        raw_t_smooth = 0.0
        _cached_n = -1
        _send_interval = 1.0 / SEND_HZ
        _last_send = 0.0
        _power_was_on = True
        print(f"[audio] opened '{mic.name}'")

        # ARC variables
        arc_avg_b = 0.0
        arc_peak_b = 0.0
        arc_mult_b = 1.0
        arc_avg_t = 0.0
        arc_peak_t = 0.0
        arc_mult_t = 1.0
        
        # Transient Envelope Tracking Arrays
        bass_avg_env = np.zeros(len(b_idx))
        treble_avg_env = np.zeros(len(t_idx))

        # Temporal smoothing for final output arrays
        r_smooth = None
        g_smooth = None
        b_smooth = None
        
        # Pre-allocated arrays to eliminate GC churn
        r_out = None
        g_out = None
        b_out = None

        try:
            with mic.recorder(samplerate=SAMPLE_RATE, blocksize=CHUNK) as rec:
                while state.running:
                    n = int(state.led_count)
                    if n != _cached_n:
                        _cached_n = n
                        r_out = np.zeros(n)
                        g_out = np.zeros(n)
                        b_out = np.zeros(n)
                        r_smooth = np.zeros(n)
                        g_smooth = np.zeros(n)
                        b_smooth = np.zeros(n)

                    data = rec.record(numframes=CHUNK)[:, 0]
                    # Hard noise gate to kill ambient floor
                    ng = getattr(state, "noise_gate", 0.002)
                    if np.sqrt(np.mean(data ** 2)) < ng:
                        client.clear_dither(n)
                        data = np.zeros_like(data)

                    fft_f = np.abs(np.fft.rfft(data))
                    if len(t_idx) > 0:
                        # Treble Transient Isolation
                        t_mags = fft_f[t_idx]
                        # Slower envelope tracking makes the transient wider and less "sparky"
                        treble_avg_env = treble_avg_env * 0.95 + t_mags * 0.05
                        transient_t = np.maximum(0, t_mags - treble_avg_env)
                        raw_t_inst = np.mean(transient_t * treble_weights) * 2.5  # Rebalanced scale
                    else:
                        raw_t_inst = 0.0
                        
                    # Asymmetric smoothing to kill the "fused capacitor" jitter
                    if raw_t_inst > raw_t_smooth:
                        raw_t_smooth = raw_t_smooth * 0.5 + raw_t_inst * 0.5   # Crisp attack
                    else:
                        raw_t_smooth = raw_t_smooth * 0.85 + raw_t_inst * 0.15 # Smooth decay
                        
                    raw_t = raw_t_smooth

                    bass_buf = np.roll(bass_buf, -CHUNK)
                    bass_buf[-CHUNK:] = data
                    fft_s = np.abs(np.fft.rfft(bass_buf * np.hanning(BASS_WINDOW)))
                    
                    if len(b_idx) > 0:
                        # Bass Transient Isolation
                        b_mags = fft_s[b_idx]
                        bass_avg_env = bass_avg_env * 0.92 + b_mags * 0.08
                        transient_b = np.maximum(0, b_mags - bass_avg_env)
                        raw_b = np.mean(transient_b * bass_weights) * 2.5  # Scale up due to transient extraction
                    else:
                        raw_b = 0.0

                    if getattr(state, "new_track_flag", False):
                        state.new_track_flag = False
                        agc.on_track_change()

                    contrast_mult = 1.0
                    if getattr(state, "dynamic_contrast", True):
                        pal = state.current_palette
                        h1 = colorsys.rgb_to_hsv(pal[0][0]/255.0, pal[0][1]/255.0, pal[0][2]/255.0)[0]
                        h2 = colorsys.rgb_to_hsv(pal[2][0]/255.0, pal[2][1]/255.0, pal[2][2]/255.0)[0]
                        hue_dist = min(abs(h1 - h2), 1.0 - abs(h1 - h2)) * 2.0 # 0.0 to 1.0
                        contrast_mult = 1.0 + 1.5 * (1.0 - hue_dist)

                    gain = agc.update(raw_b * 1.2 + raw_t, getattr(state, "extraction_mode", "cohesive")) * contrast_mult
                    bat, bde, tat, tde = state.get_attack_decay()
                    att_g = getattr(state, "attack_gamma", 1.3)
                    dec_g = getattr(state, "decay_gamma", 1.2)

                    # --- ARC (Auto Response Control) ---
                    if getattr(state, "arc_enabled", True):
                        # Laziness depends on responsiveness slider (0.0 to 1.0)
                        # Lower responsiveness -> lazier (slower) ARC evaluation
                        arc_alpha = 0.005 + (state.responsiveness * 0.045)
                        
                        # Bass ARC
                        arc_avg_b = arc_avg_b * (1 - arc_alpha) + bv * arc_alpha
                        if bv > arc_peak_b:
                            arc_peak_b = bv
                        else:
                            arc_peak_b = arc_peak_b * (1 - arc_alpha * 0.2)
                        
                        par_b = arc_peak_b / (arc_avg_b + 1e-4)
                        target_mult_b = 1.0
                        if par_b < 1.4:
                            boost = (1.4 - par_b) * 6.0
                            if getattr(state, "extraction_mode", "cohesive") == "cohesive":
                                boost *= 2.0
                            target_mult_b = 1.0 + boost * contrast_mult
                        arc_mult_b = arc_mult_b * 0.95 + target_mult_b * 0.05
                        
                        # Treble ARC
                        arc_avg_t = arc_avg_t * (1 - arc_alpha) + tv * arc_alpha
                        if tv > arc_peak_t:
                            arc_peak_t = tv
                        else:
                            arc_peak_t = arc_peak_t * (1 - arc_alpha * 0.2)
                            
                        par_t = arc_peak_t / (arc_avg_t + 1e-4)
                        target_mult_t = 1.0
                        if par_t < 1.4:
                            boost = (1.4 - par_t) * 6.0
                            if getattr(state, "extraction_mode", "cohesive") == "cohesive":
                                boost *= 2.0
                            target_mult_t = 1.0 + boost * contrast_mult
                        arc_mult_t = arc_mult_t * 0.95 + target_mult_t * 0.05
                    else:
                        arc_mult_b = 1.0
                        arc_mult_t = 1.0
                    state.live_arc_mult = max(arc_mult_b, arc_mult_t)
                    # -----------------------------------

                    # Non-linear ease-in attack and smooth accelerated fade rates:
                    # - Ease-in attack eliminates the 1st-frame maximum-velocity strobe jerk from darkness
                    # - Settling fade cleans up the asymptotic low-end tail so LEDs don't linger on 1-LSB flicker
                    # Dynamic Noise-Gate Smoother
                    # Scales attack and decay rates based on amplitude. 
                    # Huge peaks = normal fast response. Weak peaks = heavily slowed down to absorb flicker/noise.
                    noise_gate_b = min(1.0, max(0.15, raw_b * 6.0))
                    noise_gate_t = min(1.0, max(0.15, raw_t * 6.0))

                    if raw_b > bv:
                        b_rate = bat * (0.35 + 0.65 * min(1.0, bv / (raw_b + 1e-4))) * noise_gate_b
                        bv = bv + (raw_b - bv) * b_rate
                    else:
                        dec_mod = min(1.0, (bv + 1e-4) ** (dec_g - 1.0))
                        b_rate = (1.0 - bde) * (0.65 + 0.35 * dec_mod) * noise_gate_b
                        if getattr(state, "arc_enabled", True):
                            b_rate = min(1.0, b_rate * arc_mult_b)
                        bv = max(0.0, bv - (bv - raw_b) * b_rate)

                    if raw_t > tv:
                        t_rate = tat * (0.30 + 0.70 * min(1.0, tv / (raw_t + 1e-4))) * noise_gate_t
                        tv = tv + (raw_t - tv) * t_rate
                    else:
                        dec_mod = min(1.0, (tv + 1e-4) ** (dec_g - 1.0))
                        t_rate = (1.0 - tde) * (0.70 + 0.30 * dec_mod) * noise_gate_t
                        if getattr(state, "arc_enabled", True):
                            t_rate = min(1.0, t_rate * arc_mult_t)
                        tv = max(0.0, tv - (tv - raw_t) * t_rate)

                    b_amp_raw = bv * (state.bass_intensity * state.sensitivity) * gain
                    t_amp_raw = tv * (state.treble_intensity * state.sensitivity
                                      * state.treble_sens) * gain

                    # 3. Non-linear onset shaping (controlled by attack_gamma knob):
                    # Soft lift from silence cushions low-level floor noise,
                    # giving beats and transients an organic, analog bloom.
                    b_shaped = (b_amp_raw ** att_g) if b_amp_raw > 0 else 0.0
                    t_shaped = (t_amp_raw ** (att_g * 1.05)) if t_amp_raw > 0 else 0.0

                    b_amp = soft_limit(b_shaped, target_max=0.95)
                    t_amp = soft_limit(t_shaped, target_max=0.95)

                    state.live_bass = min(1.0, b_amp * 1.5)
                    state.live_treble = min(1.0, t_amp * 1.5)

                    bw = max(2.0, b_amp * state.bass_width * gain ** 0.3)
                    tw = max(2.0, 3.0 + t_amp * state.treble_width * gain ** 0.3 * 0.5)

                    lerped = []
                    for i in range(3):
                        ch = tuple(
                            state.current_palette[i][c]
                            + (state.target_palette[i][c]
                               - state.current_palette[i][c]) * 0.05
                            for c in range(3))
                        lerped.append(list(ch))
                    state.current_palette = lerped

                    c1, c2, c3 = state.current_palette
                    led_sat = state.saturation * 1.5
                    c1 = boost_saturation(c1, led_sat)
                    c2 = boost_saturation(c2, led_sat)
                    c3 = boost_saturation(c3, led_sat)

                    bg_col = get_stable_background_color(c1, state.brightness)

                    if getattr(state, "calib_mode", False):
                        cc = getattr(state, "calib_color", [0, 255, 255])
                        r_out.fill(cc[0])
                        g_out.fill(cc[1])
                        b_out.fill(cc[2])
                    elif not state.power:
                        r_out.fill(0)
                        g_out.fill(0)
                        b_out.fill(0)
                    else:
                        render_frame(
                            n, b_amp, t_amp, bw, tw, state.treble_zone,
                            bg_col, c2, c3, r_out, g_out, b_out
                        )
                    
                    # EMA low-pass filter to prevent high-frequency jittering/flickering
                    # alpha = 0.25 (25% new frame, 75% old frame)
                    alpha = getattr(state, "temporal_smoothing", 0.25)
                    r_smooth += (r_out - r_smooth) * alpha
                    g_smooth += (g_out - g_smooth) * alpha
                    b_smooth += (b_out - b_smooth) * alpha

                    # Apply global calibration multipliers
                    cr = getattr(state, "calib_r", 1.0)
                    cg = getattr(state, "calib_g", 1.0)
                    cb = getattr(state, "calib_b", 1.0)
                    r = np.clip(r_smooth * cr, 0, 255).astype(int)
                    g = np.clip(g_smooth * cg, 0, 255).astype(int)
                    b = np.clip(b_smooth * cb, 0, 255).astype(int)

                    now = time.monotonic()
                    if now - _last_send >= _send_interval:
                        if state.power or getattr(state, "calib_mode", False):
                            client.send_pixels(r, g, b)
                            _last_send = now
                            _power_was_on = True
                        elif _power_was_on:
                            # Send a few black frames to ensure UDP delivery, then stop sending
                            for _ in range(3):
                                client.send_pixels(r, g, b)
                                time.sleep(0.005)
                            _last_send = now
                            _power_was_on = False

        except Exception as e:
            print(f"[audio] error, reconnecting: {e}")
            threading.Event().wait(1)


# ── media thread ───────────────────────────────────────────────────────
async def media_loop():
    mgr = await GlobalSystemMediaTransportControlsSessionManager.request_async()
    last = ""
    while state.running:
        session = mgr.get_current_session()
        if session:
            try:
                props = await session.try_get_media_properties_async()
                if props.title != last:
                    last = props.title
                    state.current_title = props.title
                    state.current_artist = props.artist
                    state.new_track_flag = True
                    if props.thumbnail:
                        stream = await props.thumbnail.open_read_async()
                        b = bytearray(stream.size)
                        reader = DataReader(stream)
                        await reader.load_async(stream.size)
                        reader.read_bytes(b)
                        img = Image.open(io.BytesIO(b)).convert("RGB")
                        state.cached_candidates = extract_color_candidates(img)
                        state.target_palette = resolve_palette(state.cached_candidates, getattr(state, 'extraction_mode', 'cohesive'), getattr(state, 'extraction_cone', 2))
                        # 1. Fast synchronous low-res frame to trigger UI flip immediately
                        bg_low = img.resize((256, 256))
                        state.album_art_b64 = image_to_b64(bg_low, quality=60)
                        state.new_art_flag = True
                        
                        # 2. Asynchronous high-res upgrade
                        def _make_high_res(im, track_title):
                            try:
                                # Preserve original size, only scale down if it exceeds 1200x1200
                                im.thumbnail((1200, 1200), resample=Image.Resampling.LANCZOS)
                                b64 = image_to_b64(im, quality=90)
                                if state.current_title == track_title:
                                    state.album_art_b64 = b64
                            except Exception:
                                pass
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, _make_high_res, img.copy(), state.current_title)
            except Exception as e:
                print(f"[media] error: {e}")
        await asyncio.sleep(2)


# ── FastAPI ────────────────────────────────────────────────────────────
app = FastAPI()
_ws_clients: list[WebSocket] = []


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(UI_FILE, encoding="utf-8") as f:
        return f.read()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.append(ws)
    try:
        while True:
            # Drain all queued messages immediately so they never build up latency
            has_messages = True
            while has_messages:
                try:
                    raw = await asyncio.wait_for(ws.receive_text(), timeout=0.001)
                    msg = json.loads(raw)
                    if msg.get("type") == "knob":
                        state.apply_knob(msg["key"], msg["value"])
                        if msg["key"] in ("extraction_mode", "extraction_cone") and getattr(state, "cached_candidates", None):
                            try:
                                state.target_palette = resolve_palette(state.cached_candidates, getattr(state, 'extraction_mode', 'cohesive'), getattr(state, 'extraction_cone', 2))
                            except Exception as e:
                                print(f"[ui] Error resolving palette on toggle: {e}")
                    elif msg.get("type") == "window":
                        _handle_window(msg)
                    elif msg.get("type") == "reset_defaults":
                        state.reset_defaults()
                    elif msg.get("type") == "set_segments":
                        segs = msg.get("segments", [])
                        cleaned = []
                        for s in segs:
                            if isinstance(s, (list, tuple)) and len(s) >= 2:
                                try:
                                    st = max(0, int(s[0]))
                                    en = max(st + 1, int(s[1]))
                                    cleaned.append([st, en])
                                except (ValueError, TypeError):
                                    pass
                        if cleaned:
                            state.segments = cleaned
                            state.save_config()
                    elif msg.get("type") == "set_segment_mode":
                        mode = msg.get("mode")
                        if mode in ("independent", "overlay", "continuous"):
                            state.segment_mode = mode
                            state.save_config()
                except asyncio.TimeoutError:
                    has_messages = False

            await ws.send_text(json.dumps(state.to_ws_frame()))
            await asyncio.sleep(0.04)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


_window_ref = None
_miniplayer_active = False

def _handle_window(msg: dict):
    global _miniplayer_active
    if _window_ref is None: return
    action = msg.get("action")
    if action == "minimize":
        _window_ref.minimize()
    elif action == "close":
        _window_ref.hide()
    elif action == "toggle_miniplayer":
        _miniplayer_active = not _miniplayer_active
        if _miniplayer_active:
            _window_ref.resize(330, 250)
            _window_ref.on_top = True
        else:
            _window_ref.resize(500, 780)
            _window_ref.on_top = False
    elif action == "set_miniplayer":
        _miniplayer_active = msg.get("value", False)
        if _miniplayer_active:
            _window_ref.resize(330, 250)
            _window_ref.on_top = True
        else:
            _window_ref.resize(500, 780)
            _window_ref.on_top = False


# ── System Tray ────────────────────────────────────────────────────────
def setup_tray():
    image = Image.new('RGB', (64, 64), color=(0, 240, 255))

    def on_show(icon, item):
        if _window_ref:
            _window_ref.show()
            _window_ref.restore()

    def on_quit(icon, item):
        state.save_config()
        state.running = False
        icon.stop()
        if _window_ref:
            _window_ref.destroy()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem('Open Rave Mode', on_show, default=True),
        pystray.MenuItem('Quit', on_quit)
    )

    icon = pystray.Icon("rave_mode", image, "Rave Mode", menu)
    threading.Thread(target=icon.run, daemon=True).start()


# ── server ─────────────────────────────────────────────────────────────
_server_ready = threading.Event()


def start_server():
    async def _run():
        loop = asyncio.get_running_loop()
        def _handle_exc(loop, context):
            exc = context.get('exception')
            if isinstance(exc, ConnectionResetError) and getattr(exc, 'winerror', None) == 10054:
                return
            loop.default_exception_handler(context)
        loop.set_exception_handler(_handle_exc)

        cfg = uvicorn.Config(app, host="0.0.0.0", port=7373,
                             log_level="error", loop="asyncio")
        srv = uvicorn.Server(cfg)
        _server_ready.set()
        await srv.serve()

    asyncio.run(_run())


# ── entry point ────────────────────────────────────────────────────────
def main():
    global _window_ref

    client = WLEDClient()
    threading.Thread(target=audio_listener, args=(client,), daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(media_loop()), daemon=True).start()
    threading.Thread(target=check_for_updates, daemon=True).start()

    threading.Thread(target=start_server, daemon=True).start()
    _server_ready.wait(timeout=10)

    setup_tray()

    window = webview.create_window(
        "RAVE MODE",
        url="http://127.0.0.1:7373/",
        width=500,
        height=780,
        frameless=True,
        resizable=False,
        background_color="#000000",
        easy_drag=False,
    )
    _window_ref = window

    webview.start(
        debug=False,
        private_mode=False,
        storage_path=os.path.join(BASE, ".webview_cache"),
    )


if __name__ == "__main__":
    main()