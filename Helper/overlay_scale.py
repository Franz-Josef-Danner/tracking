# SPDX-License-Identifier: GPL-2.0-or-later
"""
Adaptive Tick- und Skalen-Utilities für Grafik-Overlays.

Ziele:
- Feine Skala bei kleinen Ranges (1er/0.5er/0.2er etc.)
- Grobere Skala bei großen Ranges (5, 10, 20, 50, 100, ...)
- 'Schöne' Schritte auf Basis der 1–2–5-Serie
- Optional: pixelbasierte Dichte-Steuerung (min. Abstand zwischen Labels)
"""
from __future__ import annotations
from typing import List, Tuple, Optional
import math

__all__ = (
    "nice_step",
    "nice_ticks",
    "nice_ticks_for_span",
)


def _is_finite(x: float) -> bool:
    return math.isfinite(x)


def nice_step(raw_step: float) -> float:
    """
    Rundet einen 'rohen' Schritt auf die nächstschöne 1–2–5*10^n-Stufe.
    Beispiel: 3.7 -> 5, 0.07 -> 0.05, 19 -> 20
    """
    if raw_step <= 0 or not _is_finite(raw_step):
        return 1.0
    exp = math.floor(math.log10(raw_step))
    base = 10 ** exp
    m = raw_step / base
    if m <= 1.0:
        nice = 1.0
    elif m <= 2.0:
        nice = 2.0
    elif m <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * base


def nice_ticks(
    vmin: float,
    vmax: float,
    *,
    target_ticks: int = 7,
    include_zero: bool = False,
) -> Tuple[List[float], float]:
    """
    Liefert 'schöne' Ticks im Bereich [vmin, vmax].
    - target_ticks: gewünschte Anzahl (Heuristik, kein Hard-Limit)
    - include_zero: erzwingt 0 im Tick-Set (falls im Range)
    Rückgabe: (ticks, step)
    """
    if not (_is_finite(vmin) and _is_finite(vmax)):
        return ([0.0], 1.0)
    if vmin == vmax:
        # Expandiere trivialen Bereich minimal
        span = 1.0 if vmin == 0 else abs(vmin) * 0.1
        vmin, vmax = vmin - span, vmax + span
    if vmin > vmax:
        vmin, vmax = vmax, vmin

    span = vmax - vmin
    target = max(2, int(target_ticks))
    raw_step = span / target
    step = nice_step(raw_step)

    # Starte auf einem Schritt-Raster
    start = math.floor(vmin / step) * step
    end = math.ceil(vmax / step) * step

    ticks: List[float] = []
    k = 0
    # Sicherheit gegen Endlosschleifen
    max_iter = 10000
    x = start
    while x <= end + 1e-12 and k < max_iter:
        # numerisches Runden auf vernünftige Stellen
        # (vermeidet 1.9999999998)
        r = round(x / step) * step
        ticks.append(round(r, max(0, 6 - int(math.floor(math.log10(abs(step))) if step != 0 else 0))))
        x += step
        k += 1

    if include_zero and (ticks[0] > 0.0 or ticks[-1] < 0.0):
        # 0 liegt außerhalb – ggf. Range leicht erweitern
        if 0.0 < ticks[0]:
            ticks.insert(0, 0.0)
        elif 0.0 > ticks[-1]:
            ticks.append(0.0)

    return ticks, step


def nice_ticks_for_span(
    vmax_abs: float,
    *,
    pixel_span: Optional[int] = None,
    min_label_px: int = 40,
    target_ticks: int = 7,
) -> Tuple[List[float], float]:
    """
    Variante für zentrische Skalen (0..vmax_abs) mit optionaler Pixel-Dichte.
    - pixel_span: verfügbare Pixelbreite/-höhe der Skala (falls bekannt)
    - min_label_px: gewünschter Mindestabstand zwischen Ticks (Labels)
    """
    vmax_abs = float(abs(vmax_abs))
    vmin = 0.0
    vmax = vmax_abs

    # Wenn Pixelinformationen vorhanden sind, kalibrieren wir target_ticks
    if pixel_span and pixel_span > 0 and min_label_px > 0:
        max_ticks = max(2, pixel_span // min_label_px)
        target = min(target_ticks, int(max_ticks))
    else:
        target = target_ticks
    return nice_ticks(vmin, vmax, target_ticks=target, include_zero=True)

