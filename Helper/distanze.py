""" Helper.distanze – Minimal-Neuaufbau

Aufgabe (laut Anforderung):

Beim Aufruf selektierte Marker im aktuellen Frame als "neu" erfassen.

Im gleichen Frame alle weiteren aktiven (existieren) und nicht gemuteten Marker als "alt" erfassen.

Von allen Markern die Position in Pixeln bestimmen und ins Log schreiben.

Reine Funktionsschnittstelle, wird vom tracking_coordinator aufgerufen.


Hinweise:

Marker-Koordinaten (MovieTrackingMarker.co) sind normalisiert (0..1) relativ zur Clip-Breite/-Höhe. Pixel = (co.x * width, co.y * height).

"Aktiv" bezieht sich hier auf: Für den aktuellen Frame existiert ein Marker (markers.find_frame(frame, exact=True) liefert ein Objekt) und er ist nicht gemutet (marker.mute is False).

"Selektiert" bezieht sich auf die Marker-Selektion des Keyframes (MovieTrackingMarker.select).

Es wird ein interner _solve_log()-Helper verwendet, der – falls vorhanden – die zentrale Log-Funktion des Add-ons aufruft; andernfalls wird in die Konsole gedruckt.


Rückgabe: Tuple[bool, dict]: (ok, info) ok   – True bei erfolgreicher Ausführung info – Strukturierte Daten zu Frame/Markerlisten (nützlich für Tests)

Kompatibel mit: Blender 4.x API """ from future import annotations

from typing import Any, Dict, List, Tuple

import bpy

all = ("run_distance_cleanup",)

-----------------------------------------------------------------------------

Utilities

-----------------------------------------------------------------------------

def _resolve_clip(context: bpy.types.Context): """Robust den aktiven MovieClip ermitteln.

Versucht zuerst den CLIP_EDITOR der aktuellen Area, fällt auf Szene-Clip
bzw. erstes MovieClip-Datenbankobjekt zurück.
"""
try:
    if context.area and context.area.type == "CLIP_EDITOR":
        sp = context.area.spaces.active
        if getattr(sp, "clip", None):
            return sp.clip
except Exception:
    pass

try:
    return context.scene.clip
except Exception:
    pass

try:
    return next(iter(bpy.data.movieclips), None)
except Exception:
    return None

def _solve_log(context: bpy.types.Context, value: Any) -> None: """An zentrale Solve-Log-Funktion delegieren, falls vorhanden; sonst print().""" try: import sys, importlib

root_name = (__package__ or __name__).split(".", 1)[0] or "tracking"
    mod = sys.modules.get(root_name)
    if mod and hasattr(mod, "kaiserlich_solve_log_add"):
        getattr(mod, "kaiserlich_solve_log_add")(context, value)
        return
    # Hart nachladen, falls noch nicht importiert
    mod = importlib.import_module(root_name)
    fn = getattr(mod, "kaiserlich_solve_log_add", None)
    if callable(fn):
        fn(context, value)
        return
except Exception:
    # Silent fallthrough → print
    pass
# Fallback: Konsole
try:
    print(value)
except Exception:
    pass

def _marker_pixel_pos(marker: "bpy.types.MovieTrackingMarker", width: int, height: int) -> Tuple[float, float]: """Umrechnung von Normalized- zu Pixel-Koordinaten.""" try: x = float(marker.co[0]) * float(width) y = float(marker.co[1]) * float(height) return x, y except Exception: return 0.0, 0.0

-----------------------------------------------------------------------------

Public API

-----------------------------------------------------------------------------

def run_distance_cleanup(context: bpy.types.Context) -> Tuple[bool, Dict[str, Any]]: """Erfasst selektierte (neu) und übrige aktive, ungemutete (alt) Marker im aktuellen Frame, berechnet Pixelpositionen und schreibt Log-Zeilen.

Diese Funktion verändert *keine* Marker/Tracks – sie liest nur den Status
und protokolliert ihn.
"""
clip = _resolve_clip(context)
if not clip:
    _solve_log(context, "[DISTANZE] Kein aktiver MovieClip gefunden.")
    return False, {"reason": "NO_CLIP"}

try:
    frame = int(context.scene.frame_current)
except Exception:
    frame = 0

width = int(getattr(clip, "size", (0, 0))[0]) if getattr(clip, "size", None) else 0
height = int(getattr(clip, "size", (0, 0))[1]) if getattr(clip, "size", None) else 0

tracking = getattr(clip, "tracking", None)
if not tracking:
    _solve_log(context, "[DISTANZE] Clip hat keine Tracking-Daten.")
    return False, {"reason": "NO_TRACKING"}

new_markers: List[Dict[str, Any]] = []
old_markers: List[Dict[str, Any]] = []

# 1) Selektierte Marker (NEU)
for track in getattr(tracking, "tracks", []):
    try:
        m = track.markers.find_frame(frame, exact=True)
        if not m:
            continue
        if getattr(m, "select", False):
            px, py = _marker_pixel_pos(m, width, height)
            new_markers.append(
                {
                    "track": track.name,
                    "frame": frame,
                    "muted": bool(getattr(m, "mute", False) or getattr(track, "mute", False)),
                    "co": (float(m.co[0]), float(m.co[1])),
                    "px": (px, py),
                }
            )
    except Exception:
        # Marker/Track kann in seltenen Fällen fehlerhaft sein – überspringen
        continue

# 2) Alle *anderen* aktiven & nicht gemuteten Marker (ALT)
selected_tracks = {m["track"] for m in new_markers}
for track in getattr(tracking, "tracks", []):
    try:
        m = track.markers.find_frame(frame, exact=True)
        if not m:
            continue
        # aktiv (existiert) + nicht gemutet (weder Marker noch Track)
        if bool(getattr(m, "mute", False) or getattr(track, "mute", False)):
            continue
        # nicht bereits in "neu"
        if track.name in selected_tracks and getattr(m, "select", False):
            continue
        px, py = _marker_pixel_pos(m, width, height)
        old_markers.append(
            {
                "track": track.name,
                "frame": frame,
                "muted": False,
                "co": (float(m.co[0]), float(m.co[1])),
                "px": (px, py),
            }
        )
    except Exception:
        continue

# 3) Logging – kompakt und lesbar
_solve_log(
    context,
    f"[DISTANZE] Frame {frame} | CLIP {getattr(clip, 'name', '<unnamed>')} | size=({width}x{height})",
)

def _fmt(item: Dict[str, Any]) -> str:
    return f"{item['track']}@({item['px'][0]:.1f},{item['px'][1]:.1f})"

if new_markers:
    _solve_log(context, "  NEU: " + ", ".join(_fmt(it) for it in new_markers))
else:
    _solve_log(context, "  NEU: –")

if old_markers:
    _solve_log(context, "  ALT: " + ", ".join(_fmt(it) for it in old_markers))
else:
    _solve_log(context, "  ALT: –")

info: Dict[str, Any] = {
    "frame": frame,
    "clip": getattr(clip, "name", None),
    "size": (width, height),
    "new": new_markers,
    "old": old_markers,
}

return True, info

