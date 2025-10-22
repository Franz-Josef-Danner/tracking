# Operator/track_operator_backwards.py
import bpy
from typing import List, Tuple, Dict, Deque
from collections import deque

from ..Helper.formula_helper import apply_formula_on_selected_tracks
from ..Helper.playhead_helper import get_start_frame as ph_get_start_frame, reset_to_frame
from ..Helper.scene import get_start_frame as sc_get_start_frame, get_end_frame


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------

def _find_clip_editor_area(clip):
    """Finde eine CLIP_EDITOR Area für Context Override."""
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != "CLIP_EDITOR":
                continue
            for space in area.spaces:
                if space.type != "CLIP_EDITOR":
                    continue
                if getattr(space, "clip", None) == clip or space.clip is None:
                    region_window = next((r for r in area.regions if r.type == "WINDOW"), None)
                    if region_window:
                        return window, area, region_window, space
    return None, None, None, None


def _collect_selected_track_names(context) -> List[str]:
    """Liefert Namen aller aktuell selektierten Tracks."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return []
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return []
    return [t.name for t in tracking.tracks if getattr(t, "select", False)]


def _filter_active_tracks_at_frame(context, track_names: List[str], frame: int) -> Tuple[List[str], int]:
    """Prüft, welche der Tracks im angegebenen Frame noch aktiv (nicht gemutet, Marker vorhanden) sind."""
    clip = getattr(context.space_data, "clip", None)
    if clip is None:
        return [], len(track_names)
    tracking = getattr(clip, "tracking", None)
    if tracking is None:
        return [], len(track_names)

    remaining = []
    for name in track_names:
        tr = tracking.tracks.get(name)
        if not tr:
            continue
        mk = tr.markers.find_frame(frame)
        if mk and not getattr(mk, "mute", False):
            remaining.append(name)

    dropped = len(track_names) - len(remaining)
    return remaining, dropped


# ------------------------------------------------------------
# Operator
# ------------------------------------------------------------

class KAISERLICHTRACKER_OT_track_cycle_backwards(bpy.types.Operator):
    """Trackt selektierte Marker frameweise rückwärts bis Szenenanfang, mit INVOKE_DEFAULT-Fallback."""
    bl_idname = "kaiserlich_tracker.track_cycle_backwards"
    bl_label = "Track Zyklus (Rückwärts, Frame für Frame)"
    bl_description = (
        "Trackt selektierte Marker frameweise rückwärts bis zum Szenenanfang. "
        "Erzwingt INVOKE_DEFAULT für UI-Feedback, auch bei Skriptaufrufen."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_frames: bpy.props.IntProperty(
        name="Max Frames",
        default=0,
        min=0,
        soft_max=100000,
        description="Sicherheitslimit (0 = kein Limit)"
    )

    # --------------------------------------------------------
    # invoke() — Standardstart bei UI/INVOKE_DEFAULT
    # --------------------------------------------------------
    def invoke(self, context, event):
        scene = context.scene
        current_frame = int(scene.frame_current)
        last_frame = scene.get("kaiserlich_last_frame_backwards", None)

        if last_frame == current_frame:
            print(f"[Kaiserlich Tracker][Backwards] Playhead unverändert ({current_frame}) – kein Tracking gestartet.")
            return {'CANCELLED'}

        scene["kaiserlich_last_frame_backwards"] = current_frame
        print(f"[Kaiserlich Tracker][Backwards] Starte rückwärts-Tracking ab Frame {current_frame}")
        return self._execute_tracking(context)

    # --------------------------------------------------------
    # execute() — erzwungener INVOKE_DEFAULT-Wrapper
    # --------------------------------------------------------
    def execute(self, context):
        """Wenn ohne UI gestartet, ruft sich der Operator selbst mit INVOKE_DEFAULT neu auf."""
        if not hasattr(self, "_invoked_from_ui"):
            print(f"[Kaiserlich Tracker][Backwards] Force INVOKE_DEFAULT (Re-route)")
            self._invoked_from_ui = True
            return bpy.ops.kaiserlich_tracker.track_cycle_backwards('INVOKE_DEFAULT', max_frames=self.max_frames)

        # Bereits über invoke gestartet -> echten Tracking-Code ausführen
        delattr(self, "_invoked_from_ui")
        return self._execute_tracking(context)

    # --------------------------------------------------------
    # _execute_tracking() — eigentlicher Rückwärts-Zyklus
    # --------------------------------------------------------
    def _execute_tracking(self, context):
        start_frame_saved = ph_get_start_frame(context)

        try:
            scene = context.scene
            clip = getattr(context.space_data, "clip", None)
            if clip is None:
                print("[Kaiserlich Tracker][Backwards] ❌ Kein aktiver Clip.")
                return {"CANCELLED"}

            tracking = getattr(clip, "tracking", None)
            if tracking is None:
                print("[Kaiserlich Tracker][Backwards] ❌ Kein Tracking-Objekt gefunden.")
                return {"CANCELLED"}

            frame_start = sc_get_start_frame(context)
            frame_end = get_end_frame(context)
            if frame_end < frame_start:
                frame_end = frame_start

            # Selektion sichern
            original_selected: List[str] = _collect_selected_track_names(context)
            if not original_selected:
                print("[Kaiserlich Tracker][Backwards] ❌ Keine Tracks selektiert.")
                return {"CANCELLED"}

            window, area, region, space = _find_clip_editor_area(clip)
            if not window:
                print("[Kaiserlich Tracker][Backwards] ❌ Kein CLIP_EDITOR gefunden.")
                return {"CANCELLED"}

            current_frame = int(scene.frame_current)
            if current_frame > frame_end:
                current_frame = frame_end
            if current_frame < frame_start:
                current_frame = frame_start

            space.clip_user.frame_current = current_frame
            scene.frame_current = current_frame

            processing_names: List[str] = list(original_selected)
            frames_processed = 0

            print(f"[Kaiserlich Tracker][Backwards] Tracking-Loop startet bei Frame {current_frame}")

            # --------------------------------------------------------
            # Hauptloop (rückwärts)
            # --------------------------------------------------------
            while True:
                # Stopbedingungen
                if current_frame <= frame_start:
                    print(f"[Kaiserlich Tracker][Backwards] Szenenanfang erreicht ({frame_start}).")
                    break
                if not processing_names:
                    print("[Kaiserlich Tracker][Backwards] Keine aktiven Tracks mehr.")
                    break
                if self.max_frames > 0 and frames_processed >= self.max_frames:
                    print("[Kaiserlich Tracker][Backwards] Sicherheitslimit erreicht.")
                    break

                # Optionales Preprocessing
                try:
                    apply_formula_on_selected_tracks(context, max_frames=5)
                except Exception:
                    pass

                # Tracking-Operation rückwärts
                with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
                    try:
                        bpy.ops.clip.track_markers(backwards=True, sequence=False)
                    except Exception as e:
                        print(f"[Kaiserlich Tracker][Backwards] ❌ Tracking-Fehler: {e}")
                        break

                # Fortschritt aktualisieren oder erzwingen
                if space.clip_user.frame_current == current_frame:
                    # Blender hat Playhead nicht bewegt -> manueller Schritt
                    print(f"[Kaiserlich Tracker][Backwards] Kein Move erkannt – manuell zu Frame {current_frame - 1}")
                    current_frame -= 1
                    if current_frame < frame_start:
                        print(f"[Kaiserlich Tracker][Backwards] Szenenanfang erreicht ({frame_start}).")
                        break
                    space.clip_user.frame_current = current_frame
                    scene.frame_current = current_frame
                else:
                    # Normale Bewegung
                    scene.frame_current = space.clip_user.frame_current
                    current_frame = scene.frame_current

                frames_processed += 1
                print(f"[Kaiserlich Tracker][Backwards] Frame {current_frame} getrackt ({frames_processed})")

                # Aktive Tracks prüfen
                processing_names, _ = _filter_active_tracks_at_frame(context, processing_names, current_frame)

            # Selektion am Ende wiederherstellen
            for tr in tracking.tracks:
                tr.select = (tr.name in original_selected)

            print(f"[Kaiserlich Tracker][Backwards] ✅ Tracking abgeschlossen bei Frame {scene.frame_current}")
            return {"FINISHED"}

        finally:
            # Playhead sicher zurücksetzen
            try:
                reset_to_frame(context, start_frame_saved)
            except Exception:
                pass


def register():
    bpy.utils.register_class(KAISERLICHTRACKER_OT_track_cycle_backwards)


def unregister():
    bpy.utils.unregister_class(KAISERLICHTRACKER_OT_track_cycle_backwards)
