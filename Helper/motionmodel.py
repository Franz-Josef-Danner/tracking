# tracking/Helper/motion_model.py
# -----------------------------------------------------------
# Motion Model Evaluierung für Marker-Bewegungen
# -----------------------------------------------------------

from __future__ import annotations
import bpy
from math import sqrt, atan2
from typing import Sequence, Tuple, Optional

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
    """Platzhalter – Liefert Identitätsmatrix."""
    return [
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _extract_elements(H) -> Tuple[float, float, float, float, float, float, float, float]:
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
    """Klassifiziert das Bewegungsmodell basierend auf Marker-Historie."""
    N = len(marker_positions)
    if N < 2:
        return "Loc"

    disp_var = _variance_of_step_lengths(marker_positions)

    # Dummy Homographie
    H = _find_homography_placeholder(None, None)
    a, b, c, d, tx, ty, p, q = _extract_elements(H)

    # Perspektivische Komponente?
    if abs(p) > epsilon_affine or abs(q) > epsilon_affine:
        return "Perspective"

    # Affine Komponenten
    sx = sqrt(a * a + b * b)
    sy = sqrt(c * c + d * d)
    rot_angle = atan2(b, a)
    shear = abs(a * c + b * d)

    # Modellklassifikation
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

    # Qualitätsprüfung
    mean_corr = _average(corr_values)
    if mean_corr < threshold_corr:
        if model in ("Loc", "LocRot", "LocScale"):
            model = "LocRotScale"
        elif model == "LocRotScale":
            model = "Affine"

    return model


# ---------------------------------------------------------------------------
# Blender Operator – testweise Integration
# ---------------------------------------------------------------------------

class CLIP_OT_evaluate_motion_model(bpy.types.Operator):
    """Analysiert das Bewegungsmodell des aktiven Tracks."""
    bl_idname = "clip.evaluate_motion_model"
    bl_label = "Evaluate Motion Model"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = getattr(context.space_data, "clip", None)
        if not clip:
            self.report({'WARNING'}, "Kein Clip im Movie Clip Editor aktiv.")
            return {'CANCELLED'}

        track = getattr(clip.tracking.tracks.active, "markers", None)
        if not track:
            self.report({'WARNING'}, "Kein aktiver Track ausgewählt.")
            return {'CANCELLED'}

        # Markerpositionen erfassen
        positions = [(m.frame, m.co[0], m.co[1]) for m in clip.tracking.tracks.active.markers]
        if len(positions) < 2:
            self.report({'WARNING'}, "Zu wenige Marker für Analyse.")
            return {'CANCELLED'}

        model = evaluate_motion_model(positions)
        self.report({'INFO'}, f"Erkanntes Modell: {model}")
        print(f"[MotionModel] {clip.name}: {model}")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Registrierung
# ---------------------------------------------------------------------------

def register():
    bpy.utils.register_class(CLIP_OT_evaluate_motion_model)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_evaluate_motion_model)

__all__ = ["evaluate_motion_model", "CLIP_OT_evaluate_motion_model"]