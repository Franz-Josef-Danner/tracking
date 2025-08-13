# Helper/clean_tracks_projection_error.py
# Ersatz für das frühere Dichte-Pruning: kompletter Timeline-Cleanup nach Projektion-Error.
# Schwelle wird aus scene["solve_error"] gelesen (mit Fallback), optional skaliert.

import bpy
from typing import Optional, Dict, Any, List

from .error_value import error_value  # nutzt selektierte Marker im aktiven Clip


# -- Kontext-Helfer -----------------------------------------------------------

def _get_clip_editor_handles(context: bpy.types.Context):
    """Liefert (area, region_window, space_clip) des aktiven Clip-Editors, sonst (None, None, None)."""
    screen = getattr(context, "screen", None)
    if not screen:
        return None, None, None
    for area in screen.areas:
        if area.type == 'CLIP_EDITOR':
            region_window = None
            for r in area.regions:
                if r.type == 'WINDOW':
                    region_window = r
                    break
            space = area.spaces.active
            if region_window and getattr(space, "clip", None):
                return area, region_window, space
    # Fallback: aktueller space_data (nur für Lesezugriffe)
    space = getattr(context, "space_data", None)
    if space and getattr(space, "clip", None):
        return None, None, space
    return None, None, None


def _get_clip_from_context(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    _, _, space = _get_clip_editor_handles(context)
    return getattr(space, "clip", None) if space else None


# -- Error je Track (isoliert, mit Override) ----------------------------------

def _compute_track_error_isolated(
    context: bpy.types.Context,
    scene: bpy.types.Scene,
    track: bpy.types.MovieTrackingTrack
) -> Optional[float]:
    """
    Selektiert transient GENAU diesen Track, ruft error_value(scene) im gültigen Clip-Editor-Kontext auf
    und stellt die Selektion wieder her.
    """
    area, region, space = _get_clip_editor_handles(context)
    clip = getattr(space, "clip", None) if space else None
    if not clip:
        return None

    prev_selection = {t.name: bool(t.select) for t in clip.tracking.tracks}
    try:
        # Nur Zieltrack selektieren
        for t in clip.tracking.tracks:
            t.select = (t == track)

        # error_value liest bpy.context.space_data.clip → daher mit Override ausführen
        if area and region:
            with context.temp_override(area=area, region=region, space_data=space):
                val = error_value(scene)
        else:
            # Im Notfall ohne Override (nur falls error_value robust genug ist)
            val = error_value(scene)

        return float(val) if val is not None else None
    finally:
        # Selektion wiederherstellen
        for t in clip.tracking.tracks:
            t.select = prev_selection.get(t.name, False)


# -- Track-Operationen --------------------------------------------------------

def _delete_or_mute_track(
    context: bpy.types.Context,
    track: bpy.types.MovieTrackingTrack,
    *,
    mute_only: bool = False
) -> bool:
    """
    Löscht oder mutet den gegebenen Track kontextkonform.
    """
    if mute_only:
        track.mute = True
        return True

    area, region, space = _get_clip_editor_handles(context)
    clip = getattr(space, "clip", None) if space else None
    if not clip or not area or not region:
        return False

    prev_selection = {t.name: bool(t.select) for t in clip.tracking.tracks}
    try:
        for t in clip.tracking.tracks:
            t.select = (t == track)

        with context.temp_override(area=area, region=region, space_data=space):
            res = bpy.ops.clip.delete_track(confirm=False)
            return (res == {'FINISHED'})
    finally:
        for t in clip.tracking.tracks:
            t.select = prev_selection.get(t.name, False)


# -- Hauptlogik: Cleanup über gesamte Timeline --------------------------------

def clean_tracks_by_projection_error(
    context: bpy.types.Context,
    *,
    threshold_key: str = "solve_error",
    factor: float = 1.0,
    mute_only: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Entfernt (oder mutet) Tracks, deren Projektion-Error (gemessen über error_value(scene) bei isolierter Selektion)
    die Schwelle übersteigt. Anwendung über die gesamte Timeline, kein per-Frame-Pruning.

    Schwelle = scene[threshold_key] * factor
      - threshold_key: i. d. R. "solve_error"
      - factor: Sicherheitsaufschlag (z. B. 1.2, 1.5)

    Rückgabe-Report mit Log.
    """
    scene = context.scene
    clip = _get_clip_from_context(context)
    if not clip:
        return {"status": "no_clip", "affected": 0, "threshold": None, "log": ["Kein aktiver Movie Clip."]}

    base = float(scene.get(threshold_key, 0.0))
    threshold = float(base * factor)

    log: List[str] = []
    affected = 0

    log.append(f"[ProjectionCleanup] threshold_key='{threshold_key}', base={base:.6f}, factor={factor:.3f}, threshold={threshold:.6f}")
    log.append(f"[ProjectionCleanup] Mode: {'MUTE' if mute_only else 'DELETE'}, dry_run={dry_run}")

    tracks = list(clip.tracking.tracks)

    for tr in tracks:
        err = _compute_track_error_isolated(context, scene, tr)
        if err is None:
            log.append(f"  - {tr.name}: error=None (skip)")
            continue

        if err > threshold:
            action = "mute" if mute_only else "delete"
            log.append(f"  - {tr.name}: error={err:.6f} > {threshold:.6f} → {action}")
            if not dry_run:
                ok = _delete_or_mute_track(context, tr, mute_only=mute_only)
                if not ok and not mute_only:
                    log.append(f"    ! Löschen fehlgeschlagen (Operator-Kontext?)")
                else:
                    affected += 1
        else:
            log.append(f"  - {tr.name}: error={err:.6f} ≤ {threshold:.6f} (keep)")

    return {
        "status": "ok",
        "affected": affected,
        "threshold": threshold,
        "log": log,
    }


# -- Optionaler Operator ------------------------------------------------------

class CLIP_OT_clean_tracks_projection_error(bpy.types.Operator):
    """Bereinigt Tracks über die gesamte Timeline basierend auf scene['solve_error'] * factor."""
    bl_idname = "clip.clean_tracks_projection_error"
    bl_label = "Clean Tracks by Projection Error"
    bl_options = {'REGISTER', 'UNDO'}

    factor: bpy.props.FloatProperty(
        name="Faktor",
        description="Multiplikator auf scene['solve_error']",
        default=1.0, min=0.0, soft_min=0.5, soft_max=3.0,
    )
    mute_only: bpy.props.BoolProperty(
        name="Nur muten (nicht löschen)",
        default=False,
        description="Tracks mit zu hohem Fehlerwert nur stummschalten statt löschen",
    )
    dry_run: bpy.props.BoolProperty(
        name="Dry Run (nur Log)",
        default=False,
        description="Nichts verändern, nur analysieren und Log zurückgeben",
    )
    threshold_key: bpy.props.StringProperty(
        name="Threshold Key",
        default="solve_error",
        description="Szenen-Variable mit der Solve-Error-Basis",
    )

    @classmethod
    def poll(cls, context):
        space = getattr(context, "space_data", None)
        return bool(space and getattr(space, "clip", None))

    def execute(self, context):
        report = clean_tracks_by_projection_error(
            context,
            threshold_key=self.threshold_key,
            factor=self.factor,
            mute_only=self.mute_only,
            dry_run=self.dry_run,
        )
        # Kurzes Konsolenprotokoll
        print("[CleanTracksByProjectionError] status:", report.get("status"))
        print("[CleanTracksByProjectionError] affected:", report.get("affected"))
        print("[CleanTracksByProjectionError] threshold:", report.get("threshold"))
        for line in report.get("log", []):
            print(line)

        if report.get("status") != "ok":
            self.report({'WARNING'}, "Cleanup nicht ausgeführt (kein Clip?).")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Cleanup abgeschlossen. Affected={report.get('affected', 0)}")
        return {'FINISHED'}


# -- Registrierungshelfer -----------------------------------------------------

classes = (
    CLIP_OT_clean_tracks_projection_error,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)

def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
