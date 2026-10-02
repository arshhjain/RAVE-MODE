import json, os, sys, threading

DEFAULT_IP    = '172.20.10.9'
DEFAULT_PORT  = 21324
DEFAULT_COUNT = 197

# Store config in AppData so it persists between installs and has write permissions
APP_NAME = "RaveMode"
if sys.platform == 'win32':
    APP_PATH = os.path.join(os.environ.get('APPDATA', ''), APP_NAME)
else:
    APP_PATH = os.path.expanduser(f"~/.{APP_NAME.lower()}")
os.makedirs(APP_PATH, exist_ok=True)
CONFIG_FILE = os.path.join(APP_PATH, "vibesync_config.json")

class VisualizerState:
    def __init__(self):
        self._lock   = threading.Lock()
        self.running = True

        # Network
        self.wled_ip   = ""
        self.wled_port = 21324
        self.led_count = 0

        self.calib_mode  = False
        self.calib_color = [255, 255, 255]
        self.calib_r     = 1.0
        self.calib_g     = 1.0
        self.calib_b     = 1.0

        # Main knobs
        self.power          = True
        self.sensitivity    = 0.485
        self.brightness     = 0.207
        self.saturation     = 1.0
        self.responsiveness = 0.019
        self.arc_enabled    = True
        self.isolate_rgb    = True
        self.noise_gate     = 0.008

        # Advanced knobs
        self.bass_width       = 117.1
        self.treble_width     = 98.5
        self.treble_zone      = 12.0
        self.treble_sens      = 1.607
        self.bass_intensity   = 0.199
        self.treble_intensity = 0.835
        self.attack_gamma     = 1.38
        self.decay_gamma      = 0.8
        self.extraction_mode  = "cohesive"
        self.extraction_cone  = 2  # 0=Cozy, 1=Lounge, 2=Accurate, 3=Rave
        self.dynamic_contrast = True

        # Segments & Layout
        self.segments     = []
        self.segment_mode = "independent"  # "independent", "overlay", "continuous"

        # Media
        self.current_title   = "Waiting for Music..."
        self.current_artist  = ""
        self.current_palette = [[20, 20, 20]] * 3
        self.target_palette  = [[20, 20, 20]] * 3
        self.album_art_b64   = None   # base64 JPEG for frontend background
        self.cached_candidates = []   # cached dominant color list
        self.new_art_flag    = False
        self.new_track_flag  = False

        # Live audio levels (0–1, written by audio thread)
        self.live_bass   = 0.0
        self.live_treble = 0.0

        self.load_config()
        if self.power:
            self._handle_rgb_isolation(True)

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
            "update_url":   getattr(self, "update_url", None),
            "knobs": {
                "power":            self.power,
                "sensitivity":      self.sensitivity,
                "brightness":       self.brightness,
                "saturation":       self.saturation,
                "responsiveness":   self.responsiveness,
                "arc_enabled":      self.arc_enabled,
                "isolate_rgb":      getattr(self, "isolate_rgb", True),
                "noise_gate":       getattr(self, "noise_gate", 0.002),
                "bass_width":       self.bass_width,
                "treble_width":     self.treble_width,
                "treble_zone":      self.treble_zone,
                "treble_sens":      self.treble_sens,
                "bass_intensity":   self.bass_intensity,
                "treble_intensity": self.treble_intensity,
                "attack_gamma":     self.attack_gamma,
                "decay_gamma":      self.decay_gamma,
                "extraction_mode":  getattr(self, "extraction_mode", "cohesive"),
                "dynamic_contrast": getattr(self, "dynamic_contrast", True),
                "extraction_cone":  getattr(self, "extraction_cone", 2),
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
            if key == "power" and getattr(self, "power") != value:
                self._handle_rgb_isolation(value)
            elif key == "isolate_rgb" and getattr(self, "isolate_rgb", True) != value:
                if self.power:
                    self._handle_rgb_isolation(value)
            setattr(self, key, value)
            self._schedule_save()

    def _handle_rgb_isolation(self, pause_rgb: bool):
        # pause_rgb is True when power is ON (we want to pause them)
        # or when isolate_rgb goes True while power is ON.
        # It's False when power is OFF (we want to resume them)
        # or when isolate_rgb goes False while power is ON.
        if pause_rgb and not getattr(self, "isolate_rgb", True):
            return # Don't pause if isolation is disabled
        threading.Thread(target=self._do_handle_rgb_isolation, args=(pause_rgb,), daemon=True).start()

    def _do_handle_rgb_isolation(self, pause: bool):
        try:
            import psutil
            target_procs = {
                'signalrgb.exe', 'openrgb.exe', 'icue.exe',
                'lightingservice.exe', 'rgbfusion.exe', 'ledkeeper2.exe'
            }
            count = 0
            for proc in psutil.process_iter(['name']):
                name = proc.info.get('name')
                if name and name.lower() in target_procs:
                    try:
                        if pause:
                            proc.suspend()
                            count += 1
                        else:
                            proc.resume()
                            count += 1
                    except psutil.AccessDenied:
                        print(f"[state] Access denied to {'suspend' if pause else 'resume'} {name}")
            action = "suspended" if pause else "resumed"
            print(f"[state] {count} RGB controller(s) {action}")
        except ImportError:
            print("[state] psutil not installed, cannot isolate RGB controllers")
        except Exception as e:
            print(f"[state] RGB isolation error: {e}")

    def _schedule_save(self):
        if hasattr(self, "_save_timer") and self._save_timer is not None:
            self._save_timer.cancel()
        self._save_timer = threading.Timer(0.4, self.save_config)
        self._save_timer.daemon = True
        self._save_timer.start()

    # ------------------------------------------------------------------
    def save_config(self):
        exclude = {"running", "album_art_b64", "cached_candidates", "current_title", "current_artist", "live_bass", "live_treble", "new_art_flag", "new_track_flag"}
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

    def reset_defaults(self):
        self.sensitivity    = 0.485
        self.brightness     = 0.207
        self.saturation     = 1.0
        self.responsiveness = 0.019
        self.arc_enabled    = True
        self.isolate_rgb    = True
        self.noise_gate     = 0.008
        self.bass_width       = 117.1
        self.treble_width     = 98.5
        self.treble_zone      = 12.0
        self.treble_sens      = 1.607
        self.bass_intensity   = 0.199
        self.treble_intensity = 0.835
        self.attack_gamma     = 1.38
        self.decay_gamma      = 0.8
        self._schedule_save()


state = VisualizerState()