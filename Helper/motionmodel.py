"""Motion Model Evaluierung für Marker-Bewegungen.

Diese Datei implementiert eine heuristische Klassifikation der Bewegung
eines Track-Markers basierend auf den letzten Positionsmessungen.

Modelle (Rückgabe-Strings):
    - "Loc"             : Reine Translation
    - "LocRot"          : Translation + Rotation
    - "LocScale"        : Translation + Skalierung
    - "LocRotScale"     : Translation + Rotation + uniforme Skalierung
    - "Affine"          : Allgemeine affine (inkl. Scherung / ungleichm. Skal.)
    - "Perspective"     : Signifikante perspektivische Verzerrung

Hinweis: Viele Bild-basierten Auswertungen (Homographie / Patch Analyse)
werden hier nur angedeutet, da Blender-Python im Tracking-Kontext keinen
direkten Zugriff auf die Roh-Pixel der Pattern-Patches liefert, ohne
zusätzliche Operationen. Die Funktionen sind daher als Platzhalter
implementiert und können später mit OpenCV / NumPy ersetzt werden.
"""
from __future__ import annotations

from math import sqrt, atan2
from typing import Iterable, List, Sequence, Tuple, Optional

MarkerPosition = Tuple[int, float, float]  # (frame, x_norm, y_norm)


# ---------------------------------------------------------------------------
# Interne Helfer
# ---------------------------------------------------------------------------

def _distance(p1: MarkerPosition, p2: MarkerPosition) -> float:
    return sqrt((p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2)


def _variance(values: Sequence[float]) -> float:
    n = len(values)
    if n <= 1:
        return 0.0
    m = sum(values) / n
    return sum((v - m) ** 2 for v in values) / (n - 1)


def _variance_of_step_lengths(positions: Sequence[MarkerPosition]) -> float:
    if len(positions) < 3:
        return 0.0
    steps = [_distance(positions[i], positions[i + 1]) for i in range(len(positions) - 1)]
    return _variance(steps)


def _find_homography_placeholder(_patch_a, _patch_b):
    """Platzhalter: Liefert Identitätsmatrix für Homographie."""
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _extract_elements(H) -> Tuple[float, float, float, float, float, float, float, float]:
    # H = [[a, b, tx], [c, d, ty], [p, q, 1]]
    a = H[0][0]; b = H[0][1]; tx = H[0][2]
    c = H[1][0]; d = H[1][1]; ty = H[1][2]
    p = H[2][0]; q = H[2][1]
    return a, b, c, d, tx, ty, p, q


def _average(vals: Optional[Sequence[float]]) -> float:
    if not vals:
        return 1.0
    return sum(vals) / len(vals)


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def evaluate_motion_model(
    marker_positions: Sequence[MarkerPosition],
    marker_patches: Optional[Sequence] = None,
    corr_values: Optional[Sequence[float]] = None,
    *,
    threshold_corr: float = 0.85,
    epsilon_affine: float = 1e-3,
    epsilon_rot: float = 0.0175,       # ~1°
    epsilon_scale: float = 1e-2,
) -> str:
    """Klassifiziert das Bewegungsmodell basierend auf Marker-Historie.

    Parameter
    ---------
    marker_positions : Liste von (frame, x, y) in normalisierten Clip-Koordinaten.
    marker_patches   : (Optional) Rohbild-Ausschnitte zum Start-/Endzeitpunkt.
    corr_values      : (Optional) Liste korrelativer Match-Werte (0..1).

    Returns
    -------
    str: Modellbezeichner (siehe Modul-Header).
    """
    N = len(marker_positions)
    if N < 2:
        return "Loc"  # Zu wenig Daten für komplexere Bewertung

    # 2. Translation-Analyse
    total_disp = _distance(marker_positions[0], marker_positions[-1])
    disp_var = _variance_of_step_lengths(marker_positions)

    if disp_var < 1e-9:
        base_model = "Loc"  # Gleichmäßige / keine Bewegung
    else:
        base_model = "Loc"

    # 3. Patch / Homographie Analyse (Platzhalter)
    if marker_patches and len(marker_patches) >= 2:
        H = _find_homography_placeholder(marker_patches[0], marker_patches[-1])
    else:
        H = _find_homography_placeholder(None, None)
    a, b, c, d, tx, ty, p, q = _extract_elements(H)

    # 4. Perspektive
    if abs(p) > epsilon_affine or abs(q) > epsilon_affine:
        return "Perspective"

    # 5. Affin: Skalierung / Rotation / Scherung
    sx = sqrt(a * a + b * b)
    sy = sqrt(c * c + d * d)
    rot_angle = atan2(b, a)
    shear = abs(a * c + b * d)

    # 6. Modellklassifikation
    if abs(sx - 1) < epsilon_scale and abs(sy - 1) < epsilon_scale:
        if abs(rot_angle) < epsilon_rot:
            model = "Loc"
        else:
            model = "LocRot"
    elif abs(sx - sy) < epsilon_scale and shear < epsilon_affine:
        model = "LocRotScale"
    elif shear >= epsilon_affine:
        model = "Affine"
    else:
        model = "LocScale"

    # 7. Qualitätsprüfung
    mean_corr = _average(corr_values)
    if mean_corr < threshold_corr:
        if model in ("Loc", "LocRot"):
            model = "LocRotScale"
        elif model == "LocRotScale":
            model = "Affine"

    return model


__all__ = [
    "evaluate_motion_model",
]
