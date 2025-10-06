import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.frames_limit import resolve_frames_limit
from ..Helper.track_forward import track_forward_selected_markers


class KAISERLICHTRACKER_OT_track_cycle(bpy.types.Operator):
    """Track Cycle: Fortschreiten des Playheads durch Vorwärts-Tracking selektierter Marker.

    Ablauf (vereinfacht):
      1. Bootstrap ausführen (für Zugriff auf Szenen-Endframe 'se').
      2. Aktuellen Frame (pf) bestimmen.
      3. Falls pf >= se -> fertig.
      4. Sonst bis zu N Frames (Scene-Property kaiserlich_track_frames_limit) frameweise:
         - Einen Schritt tracken (sequence=False)
         - Abbruch falls kein Tracking möglich (keine Marker selektiert / Fehler)
         - Stop wenn Szenen-Endframe erreicht.

    Hinweise:
      - Verwendet bewusst sequence=False für feingranulare Kontrolle der Schrittanzahl.
      - Falls später adaptives Limit nötig ist, kann resolve_frames_limit erweitert werden.
    """
    bl_idname = "kaiserlich_tracker.track_cycle"
    bl_label = "Track Cycle"
    bl_description = "Trackt selektierte Marker bis zum Frames-Limit oder bis zum Szenen-Endframe."
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):  # noqa: C901 (Ablauf klar, geringe Komplexität)
        scene = context.scene
        # Bootstrap benötigt die Marker-per-Frame Vorgabe (wird hier nur zur Vollständigkeit übergeben)
        ef = getattr(scene, 'kaiserlich_markers_per_frame', 25)
        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen (kein aktiver Clip)")
            return {'CANCELLED'}

        se = params.get('se')  # Szenen-Endframe (kann None sein)
        pf = scene.frame_current

        if se is not None and pf >= se:
            msg = f"Bereits am oder hinter Szenen-Endframe (pf={pf} se={se})"
            self.report({'INFO'}, msg)
            print(f"[Kaiserlich Tracker] Track Cycle: {msg}")
            return {'CANCELLED'}

        # Ermittele Frames-Limit (Scene-Property > Resolver > Fallback)
        limit_prop = getattr(scene, 'kaiserlich_track_frames_limit', 1)
        frames_limit = max(1, resolve_frames_limit(context, limit_prop))

        print("[Kaiserlich Tracker] ================= Track Cycle Start =================")
        print(f"[Kaiserlich Tracker] Startframe pf={pf} se={se} frames_limit={frames_limit}")

        frames_advanced = 0
        reason = "Unbekannt"

        while frames_advanced < frames_limit:
            # Safety: erneutes Lesen des aktuellen Frames
            pf = scene.frame_current
            if se is not None and pf >= se:
                reason = "Endframe erreicht"
                break

            ok = track_forward_selected_markers(context, sequence=False, backwards=False)
            if not ok:
                reason = "Tracking fehlgeschlagen oder keine selektierten Marker"
                break

            # Nach einem erfolgreichen Schritt sollte Blender den aktuellen Frame erhöht haben.
            frames_advanced += 1

        else:
            reason = "Frames-Limit erreicht"

        pf_end = scene.frame_current
        total_msg = (f"Vorgerückt: {frames_advanced} Frames | pf Ende={pf_end}" +
                     (f" / se={se}" if se is not None else "") +
                     f" | Grund: {reason}")
        print(f"[Kaiserlich Tracker] Track Cycle: {total_msg}")
        print("[Kaiserlich Tracker] ================= Track Cycle Ende ==================")
        self.report({'INFO'}, total_msg)
        return {'FINISHED'}


__all__ = [
    'KAISERLICHTRACKER_OT_track_cycle',
]
