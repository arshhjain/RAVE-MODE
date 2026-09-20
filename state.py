import json, os, threading

DEFAULT_IP    = '172.20.10.9'
DEFAULT_PORT  = 21324
DEFAULT_COUNT = 197

APP_PATH    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_PATH, "vibesync_config.json")

class VisualizerState:
    def __init__(self):
        self._lock   = threading.Lock()
        self.running = True

        # Network
        self.wled_ip   = DEFAULT_IP
        self.wled_port = DEFAULT_PORT
        self.led_count = DEFAULT_COUNT

        self.calib_mode  = False
        self.calib_color = [0, 255, 255]
        self.calib_r     = 1.0
        self.calib_g     = 1.0
        self.calib_b     = 1.0

        # Main knobs
        self.power          = True
        self.sensitivity    = 0.8
        self.brightness     = 0.2
        self.saturation     = 1.0
        self.responsiveness = 0.5
        self.arc_enabled    = True

        # Advanced knobs
        self.bass_width       = 30.0
        self.treble_width     = 30.0
        self.treble_zone      = 10.0
        self.treble_sens      = 1.0
        self.bass_intensity   = 0.08
        self.treble_intensity = 0.6
        self.attack_gamma     = 1.3
        self.decay_gamma      = 1.2

        # Segments & Layout
        self.segments     = [[0, 73], [73, 107], [107, 163], [163, 197]]
        self.segment_mode = "independent"  # "independent", "overlay", "continuous"

        # Media
        self.current_title   = "Waiting for Music..."
        self.current_artist  = ""
        self.current_palette = [[20, 20, 20]] * 3
        self.target_palette  = [[20, 20, 20]] * 3
        self.album_art_b64   = None   # base64 JPEG for frontend background
        self.new_art_flag    = False
        self.new_track_flag  = False

        # Live audio levels (0–1, written by audio thread)
        self.live_bass   = 0.0
        self.live_treble = 0.0

        self.load_config()

    # ------------------------------------------------------------------
    def get_attack_decay(self):
        r = self.responsiveness
        # Bass: fast punch, smooth sustain
        bat = 0.10 + r * 0.75
        bde = 0.95 - r * 0.45
        # Treble: smooth out jitter with stable decay retention
        tat = 0.15 + r * 0.55
        tde = 0.94 - r * 0.30
        return (bat, bde, tat, tde)

    # ------------------------------------------------------------------
    def to_ws_frame(self):
        """Snapshot for WebSocket broadcast — no lock needed (GIL is fine here)."""
        # Cast palette to plain Python ints — numpy float32 is not JSON serializable
        palette = [[int(v) for v in colour] for colour in self.current_palette]
        return {
            "title":        self.current_title,
            "artist":       self.current_artist,
            "palette":      palette,
            "bass":         round(float(self.live_bass),   3),
            "treble":       round(float(self.live_treble), 3),
            "arc_mult":     round(float(getattr(self, 'live_arc_mult', 1.0)), 2),
            "art":          self.album_art_b64,
            "segments":     self.segments,
            "segment_mode": self.segment_mode,
            "knobs": {
                "power":            self.power,
                "sensitivity":      self.sensitivity,
                "brightness":       self.brightness,
                "saturation":       self.saturation,
                "responsiveness":   self.responsiveness,
                "arc_enabled":      self.arc_enabled,
                "bass_width":       self.bass_width,
                "treble_width":     self.treble_width,
                "treble_zone":      self.treble_zone,
                "treble_sens":      self.treble_sens,
                "bass_intensity":   self.bass_intensity,
                "treble_intensity": self.treble_intensity,
                "attack_gamma":     self.attack_gamma,
                "decay_gamma":      self.decay_gamma,
                "led_count":        self.led_count,
                "wled_ip":          self.wled_ip,
                "wled_port":        self.wled_port,
                "calib_mode":       self.calib_mode,
                "calib_color":      self.calib_color,
                "calib_r":          self.calib_r,
                "calib_g":          self.calib_g,
                "calib_b":          self.calib_b,
            }
        }

    # ------------------------------------------------------------------
    def apply_knob(self, key, value):
        if hasattr(self, key):
            setattr(self, key, value)
            self._schedule_save()

    def _schedule_save(self):
        if hasattr(self, "_save_timer") and self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.4, self.save_config)
        self._save_timer.daemon = True
        self._save_timer.start()

    # ------------------------------------------------------------------
    def save_config(self):
        exclude = {"running", "album_art_b64", "current_title", "current_artist", "live_bass", "live_treble", "new_art_flag", "new_track_flag"}
        data = {k: v for k, v in self.__dict__.items()
                if k not in exclude and type(v) in (float, int, str, list)}
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[state] save failed: {e}")

    def load_config(self):
        if not os.path.exists(CONFIG_FILE): return
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
            for k, v in data.items():
                if hasattr(self, k): setattr(self, k, v)
        except Exception as e:
            print(f"[state] load failed: {e}")


state = VisualizerState()