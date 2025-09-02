from __future__ import annotations
import bpy
from typing import Iterable, Set, Any
import sys, importlib

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

# Optional unterstützte Alias-Schlüssel (falls historisch abweichend)
ALIAS_LIST_KEYS: Iterable[str] = (
    "kc_solve_errors",
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

def _clear_list_in_place(container: Any, key: str) -> bool:
    """Leert vorhandene Listen-ID-Props in-place (keine Referenzleichen)."""
    try:
        if key in container.keys():
            val = container[key]
            if isinstance(val, list):
                val.clear()
                container[key] = val  # Re-write sichert Speicherung
                return True
    except Exception:
        pass
    return False

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
        if not _clear_list_in_place(scene, key):
            scene[key] = []         # Fallback: ersetzen
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
        # Auch am Clip vorhandene kc_*-Solve-Listen konsequent leeren
        for k in ("kc_error_solves", "kc_solve_errors", "kc_avg_error_history"):
            try:
                if k in clip.keys():
                    v = clip[k]
                    if isinstance(v, list):
                        v.clear()
                        clip[k] = v
            except Exception:
                pass
        # Verwaiste kc_* Keys am Clip purgen (ohne Defaults zu setzen)
        allow = set(RUNTIME_KEYS) | set(ALIAS_LIST_KEYS)
        for k in list(clip.keys()):
            if str(k).startswith("kc_") and k not in allow:
                try:
                    del clip[k]
                except Exception:
                    pass
    except Exception:
        pass

def _reset_module_solve_log() -> int:
    """
    Räumt modulweite Solve-Logs auf (Root-Paket + 'tracking' Fallback).
    - Ruft kaiserlich_solve_log_reset() auf, wenn vorhanden.
    - Leert bekannte Container-Attribute in-place.
    Gibt die Anzahl der bereinigten Container zurück.
    """
    cleared = 0
    candidates = []
    # Root aus __package__/__name__ ableiten (analog zum Coordinator)
    root_name = (__package__ or __name__).split(".", 1)[0] or "tracking"
    candidates.append(root_name)
    if "tracking" not in candidates:
        candidates.append("tracking")
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        mod = sys.modules.get(name)
        if not mod:
            try:
                mod = importlib.import_module(name)
            except Exception:
                mod = None
        if not mod:
            continue
        # 1) Reset-Funktion
        fn = getattr(mod, "kaiserlich_solve_log_reset", None)
        if callable(fn):
            try:
                fn()
                cleared += 1
            except Exception:
                pass
        # 2) Bekannte Container leeren
        for attr in ("kaiserlich_solve_log", "SOLVE_LOG", "solve_log"):
            lst = getattr(mod, attr, None)
            if isinstance(lst, list):
                try:
                    lst.clear()
                    cleared += 1
                except Exception:
                    pass
    return cleared

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
    # 1b) Aliase ebenfalls leeren (falls historisch genutzt)
    for alias in ALIAS_LIST_KEYS:
        _clear_list_in_place(scene, alias)

    # Aktiven Clip finden und temporäre Auswahlen zurücksetzen
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip and bpy.data.movieclips:
        clip = next(iter(bpy.data.movieclips), None)
    _wipe_clip_runtime(clip)

    # 2) Modulweite Solve-Logs/Caches bereinigen
    _reset_module_solve_log()

    # 2b) Solve-Error Log (CollectionProperty) explizit zurücksetzen
    try:
        if hasattr(scene, "kaiserlich_solve_err_log"):
            scene.kaiserlich_solve_err_log.clear()
        if hasattr(scene, "kaiserlich_solve_attempts"):
            scene.kaiserlich_solve_attempts = 0
    except Exception:
        pass

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
        kc_count = sum(1 for k in scene.keys() if str(k).startswith("kc_"))
        log_len = len(scene.kaiserlich_solve_err_log) if hasattr(scene, "kaiserlich_solve_err_log") else -1
        print(f"[Reset] purged={purged} kc_count={kc_count} clip={cname} solve_log_len={log_len}")
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
