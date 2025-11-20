# Helper.validate_motion_backward_helper.py
from __future__ import annotations
import bpy
from typing import List


# ============================================================
# Hilfsfunktion: Marker-Positionen (Vorwärts) für BW-Prüfung
# ============================================================
def _get_positions_backward(track: bpy.types.MovieTrackingTrack,
                            current_frame: int,
                            max_frames: int = 4) -> List[tuple[int, tuple[float, float]]]:

    positions = []
    markers = track.markers
    end = current_frame + max_frames

    print(f"[BW-GetPos] Track={track.name} Frames={current_frame}→{end}")

    for frame in range(current_frame, end + 1):
        marker = markers.find_frame(frame, exact=True)
        if not marker:
            print(f"   • Frame {frame}: kein Marker")
            continue
        if not marker.co:
            print(f"   • Frame {frame}: Marker ohne Koordinaten")
            continue

        co = marker.co.copy()
        positions.append((frame, co))
        print(f"   • Frame {frame}: pos=({co[0]:.6f}, {co[1]:.6f})")

    return positions


# ============================================================
# Track-Lister
# ============================================================
def _resolve_reference_track_names(scene: bpy.types.Scene) -> List[str]:
    if scene.get("best_tracks"):
        names = scene.get("best_tracks_names", [])
        print(f"[BW-ResolveRef] best_tracks={len(names)}")
        return [n for n in names if isinstance(n, str) and n.strip()]

    if scene.get("good_tracks"):
        names = scene.get("good_tracks_names", [])
        print(f"[BW-ResolveRef] good_tracks={len(names)}")
        return [n for n in names if isinstance(n, str) and n.strip()]

    print("[BW-ResolveRef] Keine best/good Tracks gefunden.")
    return []


def _resolve_calibrate_track_names(scene: bpy.types.Scene) -> List[str]:
    if not scene.get("calibrate_tracks"):
        print("[BW-ResolveCal] Keine calibrate_tracks.")
        return []
    names = scene.get("calibrate_tracks_names", [])
    print(f"[BW-ResolveCal] calibrate_tracks={len(names)}")
    return [n for n in names if isinstance(n, str) and n.strip()]


# ============================================================
# Haupt-Routine: Validiert BW-Bewegung anhand FW-Deltas
# ============================================================
def validate_calibrate_tracks_backward_window(context: bpy.types.Context) -> None:
    scene = context.scene
    clip = getattr(context.space_data, "clip", None)

    print("\n======= [Validate Backward Motion Window] =======")

    if clip is None:
        print("[ValidateBW] ❌ Kein Clip gefunden → Abbruch.")
        return

    # ---- Namen laden ----
    ref_list = _resolve_reference_track_names(scene)
    if not ref_list:
        print("[ValidateBW] ⏭️ Skip BW-Check (keine Reference Tracks vorhanden).")
        return  # wichtig: kein Fehler, einfach Skip

    calibrate_list = _resolve_calibrate_track_names(scene)
    if not calibrate_list:
        print("[ValidateBW] ❌ Keine calibrate_tracks → Abbruch.")
        return

    current_frame = scene.frame_current
    print(f"[ValidateBW] CurrentFrame={current_frame}")

    # ---- Referenz-Vektoren sammeln ----
    dx_values, dy_values = [], []

    print("\n--- [Reference Vector Calculation] ---")
    for name in ref_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            print(f"   • REF {name}: ❌ nicht gefunden")
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            print(f"   • REF {name}: ⚠️ zu wenige Marker ({len(pos)})")
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx = x1 - x2
        dy = y1 - y2

        dx_values.append(dx)
        dy_values.append(dy)

        print(f"   • REF {name}: Δx={dx:.6f} Δy={dy:.6f}")

    if not dx_values or not dy_values:
        print("[ValidateBW] ❌ Keine gültigen Bewegungsvektoren → Abbruch.")
        return

    avg_dx = sum(dx_values) / len(dx_values)
    avg_dy = sum(dy_values) / len(dy_values)
    print(f"\n[REF AVG] Δx={avg_dx:.6f} Δy={avg_dy:.6f}")

    # ---- Threshold bestimmen ----
    max_dev = getattr(scene, "max_error_value", 5.0) / 100.0
    print(f"[Threshold] max_dev={max_dev:.6f} (aus scene.max_error_value)")

    # ---- Calibrate-Tracks prüfen ----
    print("\n--- [Calibrate Validation] ---")
    for name in calibrate_list:
        track = clip.tracking.tracks.get(name)
        if not track:
            print(f"   • CAL {name}: ❌ nicht gefunden")
            continue

        pos = _get_positions_backward(track, current_frame, 4)
        if len(pos) < 2:
            print(f"   • CAL {name}: ⚠️ zu wenige Marker ({len(pos)})")
            continue

        (_, (x1, y1)), (_, (x2, y2)) = pos[0], pos[1]
        dx = x1 - x2
        dy = y1 - y2

        dev_x = abs(dx - avg_dx)
        dev_y = abs(dy - avg_dy)

        print(f"   • CAL {name}: Δx={dx:.6f} Δy={dy:.6f} | DevX={dev_x:.6f}, DevY={dev_y:.6f}")

        if dev_x > max_dev or dev_y > max_dev:
            marker = track.markers.find_frame(current_frame, exact=True)
            if marker:
                marker.mute = True
                print(f"     → ❌ MUTED @ {current_frame}: Track {name} (abweichend!)")
            else:
                print(f"     → ⚠️ Kein Marker @ {current_frame}, keine Stummschaltung möglich.")

    print("======= [END Validate Backward Motion] =======\n")
