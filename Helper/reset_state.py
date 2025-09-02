from __future__ import annotations
import bpy
from typing import Iterable, Set

__all__ = ("reset_for_new_cycle", "CLIP_OT_reset_runtime_state")

# Einheitliche Präfixe für Runtime-Variablen dieses Add-ons.
RUNTIME_KEYS: Iterable[str] = (
    # Zähler/Indikatoren
    "kc_cycle_index",
    "kc_solve_attempts",
    "kc_findlow_finished",
    "kc_findmax_finished",
    "kc_projection_cleanup_runs",
    # Schwellwerte/Parameter
    "kc_spike_threshold",
    "kc_spike_floor",
    "kc_spike_decay",
    "kc_error_track_target",
    "kc_refine_intrinsics_focal_length",
    # Sammlungen/Listen
    "kc_avg_error_history",
    "kc_marker_counts",
    "kc_log_rows",
    "kc_last_frames_checked",
    "kc_error_solves",        # Liste aller Solve-Errors → beim Reset leeren
    # Mappings/Dicts
    "kc_repeat_frame",
)

def _purge_unknown_kc_keys(scene: bpy.types.Scene, allow: Set[str]) -> int:
    """Entfernt verwaiste kc_* ID-Props, die nicht mehr in RUNTIME_KEYS gelistet sind."""
    removed = 0
    try:
        # keys() liefert nur ID-Props, nicht RNA-Properties
        for k in list(scene.keys()):
            if isinstance(k, str) and k.startswith("kc_") and k not in allow:
                try:
                    del scene[k]
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removed

def _set_default(scene: bpy.types.Scene, key: str) -> None:
    """Definiert robuste Default-Werte pro Key (ID-Properties!)."""
    if key == "kc_cycle_index":
        scene[key] = 0
    elif key == "kc_solve_attempts":
        scene[key] = 0
    elif key in {"kc_findlow_finished", "kc_findmax_finished"}:
        scene[key] = False
    elif key == "kc_projection_cleanup_runs":
        scene[key] = 0
    elif key == "kc_spike_threshold":
        scene[key] = 100.0     # Startwert für SPIKE_CYCLE
    elif key == "kc_spike_floor":
        scene[key] = 10.0       # Abbruchschwelle
    elif key == "kc_spike_decay":
        scene[key] = 0.9        # Multiplikativer Decay
    elif key == "kc_error_track_target":
        scene[key] = 2.0        # Zielwert für avg reprojection error
    elif key == "kc_refine_intrinsics_focal_length":
        scene[key] = False      # erster Solve ohne Refine
    elif key in {
        "kc_avg_error_history",
        "kc_marker_counts",
        "kc_log_rows",
        "kc_last_frames_checked",
        "kc_error_solves",
    }:
        scene[key] = []         # Listen konsequent leeren
    elif key == "kc_repeat_frame":
        scene[key] = {}         # Wiederhol-Map (Frame -> Count)
    else:
        # Fallback: entfernen, falls als ID-Prop gesetzt
        try:
            if key in scene.keys():
                del scene[key]
        except Exception:
            scene[key] = None

def _wipe_clip_runtime(clip: bpy.types.MovieClip | None) -> None:
    """Clip-/Tracking-bezogene volatile Stati zurücksetzen (nicht: Tracks löschen!)."""
    if not clip:
        return
    # Deselect all to start clean – wir verändern KEINE Daten-Inhalte.
    try:
        tr = clip.tracking
        for track in tr.tracks:
            track.select = False
        for obj in tr.objects:
            for t in obj.tracks:
                t.select = False
    except Exception:
        pass

def reset_for_new_cycle(context: bpy.types.Context) -> None:
    """
    Zentrale Reset-Funktion für den Neustart des Ablaufs.
    - Setzt alle bekannten Runtime-Werte auf Defaults
    - Bereinigt temporäre Selektionen am aktiven Clip
    - Verändert keine persistenten Projektdaten (keine Marker-/Track-Löschungen)
    """
    scene = context.scene
    # 0) Altlasten entfernen (verwaiste kc_* Keys)
    purged = _purge_unknown_kc_keys(scene, allow=set(RUNTIME_KEYS))
    # 1) Scene-Keys konsistent initialisieren/überschreiben
    for k in RUNTIME_KEYS:
        _set_default(scene, k)

    # Aktiven Clip finden und temporäre Auswahlen zurücksetzen
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    _wipe_clip_runtime(clip)

    # Optional: UI-Refresh, damit Panels frische Werte anzeigen
    try:
        for area in context.window.screen.areas:
            if area.type in {"CLIP_EDITOR", "VIEW_3D", "PROPERTIES"}:
                area.tag_redraw()
    except Exception:
        pass

    # 3) Minimaler Konsistenz-Log
    try:
        clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None)
        cname = getattr(clip, "name", "<none>")
        # Anzahl aktuell gesetzter kc_* Keys
        kc_count = sum(1 for k in scene.keys() if str(k).startswith("kc_"))
        print(f"[Reset] purged={purged} kc_count={kc_count} clip={cname}")
    except Exception:
        pass


class CLIP_OT_reset_runtime_state(bpy.types.Operator):
    """Setzt alle laufzeitgenerierten Kaiserlich-Tracker States zurück (ID-Props & Selektionen)."""
    bl_idname = "clip.kc_reset_runtime_state"
    bl_label = "Reset Runtime State"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context):  # type: ignore[override]
        try:
            reset_for_new_cycle(context)
            self.report({"INFO"}, "Runtime-State zurückgesetzt.")
            return {"FINISHED"}
        except Exception as exc:  # pragma: no cover - defensive
            self.report({"ERROR"}, f"Reset fehlgeschlagen: {exc}")
            return {"CANCELLED"}
