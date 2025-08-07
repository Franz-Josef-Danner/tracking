# ram_helper.py
# Kleiner RAM-Guard für Blender-Add-ons.
# Abhängigkeit: psutil (in Blender-Python installieren, s.u.)

import time

try:
    import psutil
except Exception:
    psutil = None


class RamGuard:
    """
    Simple Schwellenwächter mit Hysterese + Cooldown.
    Verwendung:
        guard = RamGuard(threshold_up=90, threshold_down=80, cooldown=5)
        event, pct = guard.poll()
        if event == 'enter_hot':
            # hier dein Proxy-Pulse aufrufen
    Events: 'enter_hot', 'exit_hot', None
    """

    def __init__(self,
                 threshold_up: float = 90.0,
                 threshold_down: float = 80.0,
                 cooldown: float = 5.0,
                 smooth_samples: int = 1):
        assert threshold_down <= threshold_up, "threshold_down <= threshold_up erwartet"
        self.threshold_up = float(threshold_up)
        self.threshold_down = float(threshold_down)
        self.cooldown = float(cooldown)
        self.smooth_samples = max(1, int(smooth_samples))

        self._state_hot = False
        self._last_action = 0.0
        self._buf = []

    # --- Messung ---
    @staticmethod
    def percent() -> float | None:
        """System-RAM in %, None wenn psutil fehlt."""
        if psutil is None:
            return None
        return float(psutil.virtual_memory().percent)

    # --- Logik ---
    def poll(self) -> tuple[str | None, float | None]:
        """
        Einmal aufrufen (z.B. pro TIMER-Tick). Gibt (event, percent) zurück.
        event: 'enter_hot' | 'exit_hot' | None
        percent: letzter gemessener RAM-% (oder None ohne psutil)
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
