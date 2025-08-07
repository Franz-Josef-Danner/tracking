# Helper/ram_helper.py
# RamGuard mit Self-Bootstrap für psutil (lokal in Helper/vendor)
import os, sys, subprocess, importlib, time

psutil = None  # wird beim Bootstrap gesetzt

def ensure_psutil(auto_install=True, target_dir=None, logger=print):
    """
    Stellt sicher, dass psutil importierbar ist.
    - Installiert optional via pip in ein lokales 'vendor'-Verzeichnis neben dieser Datei.
    - Fügt target_dir zu sys.path hinzu und importiert psutil.
    Rückgabe: (ok: bool, psutil_or_none, msg: str)
    """
    global psutil
    # Schon geladen?
    if psutil is not None:
        return True, psutil, "psutil bereits initialisiert"
    # Schon importierbar?
    try:
        import psutil as _ps
        psutil = _ps
        return True, psutil, "psutil bereits vorhanden"
    except Exception:
        if not auto_install:
            return False, None, "psutil nicht vorhanden und auto_install=False"

    # --- Installation vorbereiten ---
    try:
        import ensurepip
        ensurepip.bootstrap()
    except Exception as e:
        return False, None, f"ensurepip fehlgeschlagen: {e}"

    if target_dir is None:
        target_dir = os.path.join(os.path.dirname(__file__), "vendor")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        return False, None, f"vendor-Verzeichnis fehlgeschlagen: {e}"

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "psutil", "--target", target_dir]
    try:
        logger(f"🔧 psutil-Installation in: {target_dir}")
        rc = subprocess.call(cmd)
        if rc != 0:
            return False, None, f"pip rc={rc}"
    except Exception as e:
        return False, None, f"pip-Call fehlgeschlagen: {e}"

    if target_dir not in sys.path:
        sys.path.insert(0, target_dir)
    importlib.invalidate_caches()

    try:
        import psutil as _ps
        psutil = _ps
        return True, psutil, "psutil installiert"
    except Exception as e:
        return False, None, f"Import nach Installation fehlgeschlagen: {e}"


class RamGuard:
    """
    Schwellenwächter mit Hysterese + Cooldown.
      guard = RamGuard(threshold_up=90, threshold_down=80, cooldown=5)
      event, pct = guard.poll()
      if event == 'enter_hot':  # hier Proxy-Flush triggern

    Events: 'enter_hot', 'exit_hot', 'no_psutil', None
    """

    def __init__(self,
                 threshold_up: float = 90.0,
                 threshold_down: float = 80.0,
                 cooldown: float = 5.0,
                 smooth_samples: int = 1,
                 auto_install_psutil: bool = True,
                 vendor_dir: str | None = None,
                 logger=print):
        assert threshold_down <= threshold_up, "threshold_down <= threshold_up erwartet"
        self.threshold_up = float(threshold_up)
        self.threshold_down = float(threshold_down)
        self.cooldown = float(cooldown)
        self.smooth_samples = max(1, int(smooth_samples))
        self._state_hot = False
        self._last_action = 0.0
        self._buf = []

        # psutil sicherstellen (Self-Bootstrap)
        ok, _mod, _msg = ensure_psutil(auto_install=auto_install_psutil, target_dir=vendor_dir, logger=logger)
        # ok kann False sein (offline etc.) -> poll() liefert dann 'no_psutil'

    # --- Messung ---
    def percent(self) -> float | None:
        """System-RAM in %, None wenn psutil weiterhin fehlt."""
        if psutil is None:
            return None
        try:
            return float(psutil.virtual_memory().percent)
        except Exception:
            return None

    # --- Logik ---
    def poll(self) -> tuple[str | None, float | None]:
        """
        Einmal aufrufen (z.B. pro TIMER-Tick). Gibt (event, percent) zurück.
        event: 'enter_hot' | 'exit_hot' | 'no_psutil' | None
        percent: letzter RAM-% (oder None ohne psutil)
        """
        p = self.percent()
        if p is None:
            return 'no_psutil', None

        # optional glätten
        if self.smooth_samples > 1:
            self._buf.append(p)
            if len(self._buf) > self.smooth_samples:
                self._buf.pop(0)
            p = sum(self._buf) / len(self._buf)

        now = time.time()
        cooldown_over = (now - self._last_action) >= self.cooldown
        event = None

        if not self._state_hot and p >= self.threshold_up and cooldown_over:
            self._state_hot = True
            self._last_action = now
            event = 'enter_hot'
        elif self._state_hot and p <= self.threshold_down and cooldown_over:
            self._state_hot = False
            self._last_action = now
            event = 'exit_hot'

        return event, p

    def should_pulse(self) -> tuple[bool, float | None]:
        """True genau beim Übergang in HOT (inkl. Cooldown/Hysterese)."""
        event, p = self.poll()
        return (event == 'enter_hot'), p


# Optional: Timer-Integration ohne eigenen Modal-Op
def register_bpy_timer(guard: RamGuard, on_enter_hot, on_exit_hot=None,
                       interval: float = 1.0, stop_flag=lambda: False):
    """
    Registriert einen bpy.app.timers-Loop, der Events an Callbacks feuert.
    Callbacks laufen im Main-Thread -> dort erst deine Proxy-Helper aufrufen!
    Rückgabewert: die von bpy.app.timers.register zurückgegebene Funktion (zum Deregistrieren None zurückgeben).
    """
    import bpy  # import hier, damit Modul auch außerhalb Blender testbar ist

    def _tick():
        if stop_flag():
            return None
        event, _pct = guard.poll()
        if event == 'enter_hot' and on_enter_hot:
            on_enter_hot(_pct)
        elif event == 'exit_hot' and on_exit_hot:
            on_exit_hot(_pct)
        return interval

    return bpy.app.timers.register(_tick, first_interval=interval)
    # Bequemlichkeit: direkt fragen, ob man „pulsen“ soll
    def should_pulse(self) -> tuple[bool, float | None]:
        """True genau beim Übergang in HOT (inkl. Cooldown/Hysterese)."""
        event, p = self.poll()
        return (event == 'enter_hot'), p


# Optional: Timer-Integration ohne eigenen Modal-Op
def register_bpy_timer(guard: RamGuard, on_enter_hot, on_exit_hot=None,
                       interval: float = 1.0, stop_flag=lambda: False):
    """
    Registriert einen bpy.app.timers-Loop, der Events an Callbacks feuert.
    Callbacks laufen im Main-Thread -> dort erst deine Proxy-Helper aufrufen!
    Rückgabewert: die von bpy.app.timers.register zurückgegebene Funktion (zum Deregistrieren None zurückgeben).
    """
    import bpy  # import erst hier, damit Modul auch außerhalb Blender testbar ist

    def _tick():
        if stop_flag():
            return None
        event, _pct = guard.poll()
        if event == 'enter_hot' and on_enter_hot:
            on_enter_hot(_pct)
        elif event == 'exit_hot' and on_exit_hot:
            on_exit_hot(_pct)
        return interval

    return bpy.app.timers.register(_tick, first_interval=interval)
