# main.py – Clean-free Version
import bpy
from bpy.types import Operator

from ..Helper.find_low_marker_frame import find_low_marker_frame
from ..Helper.jump_to_frame import jump_to_frame
from ..Helper.properties import RepeatEntry  # CollectionProperty-Einträge
from ..Helper.solve_camera_helper import CLIP_OT_solve_watch_clean, run_solve_watch_clean


class CLIP_OT_main(Operator):
    bl_idname = "clip.main"
    bl_label = "Main Setup (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # Externe Ableitung zur Anpassung von Marker-Bounds (optional)
    marker_adapt: bpy.props.IntProperty(
        name="Marker Adapt",
        description="Extern übergebener Ableitungswert für Marker-Bounds",
        default=0, min=0
    )

    _timer = None
    _step = 0

    def execute(self, context):
        scene = context.scene

        # Laufzeit-Flags initialisieren
        scene["solve_status"] = ""
        scene["solve_error"] = -1.0
        scene["solve_watch_fallback"] = False
        scene["pipeline_status"] = ""
        scene["marker_min"] = 0
        scene["marker_max"] = 0
        scene["goto_frame"] = -1

        # Error-Limit Snapshot (unverändert)
        try:
            scene["error_limit_run"] = float(getattr(scene, "error_track"))
        except Exception:
            scene["error_limit_run"] = float(scene.get("error_track", 0.0))

        # Repeat-Collection leeren (falls vorhanden)
        if hasattr(scene, "repeat_frame"):
            scene.repeat_frame.clear()

        # Gültigen Clip sicherstellen
        space = getattr(context, "space_data", None)
        clip = getattr(space, "clip", None)
        if clip is None or not getattr(clip, "tracking", None):
            self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
            return {'CANCELLED'}

        # Gatekeeper vor dem ersten Zyklus
        marker_basis = int(scene.get("marker_basis", 25))
        pre_frame = find_low_marker_frame(clip, marker_basis=marker_basis)
        if pre_frame is None:
            print("✅ Vorprüfung: Keine Low-Marker-Frames. Prozess wird beendet.")
            self.report({'INFO'}, "Keine Low-Marker-Frames – nichts zu tun.")
            return {'FINISHED'}
        else:
            scene["goto_frame"] = int(pre_frame)
            jump_to_frame(context)
            print(f"🎯 Vorprüfung: Low-Marker-Frame {pre_frame} – starte Pipeline ab diesem Frame.")

        # Vorbereitungen (beibehalten)
        print("🚀 Starte Tracking-Vorbereitung...")
        bpy.ops.clip.tracker_settings('EXEC_DEFAULT')
        bpy.ops.clip.marker_helper_main('EXEC_DEFAULT')

        # Tracking-Pipeline starten
        print("🚀 Starte Tracking-Pipeline...")
        bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
        print("⏳ Warte auf Abschluss der Pipeline...")

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.5, window=context.window)
        wm.modal_handler_add(self)
        self._step = 0
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            self._teardown(context, cancelled=True)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        # Step 0: Warten bis Pipeline fertig
        if self._step == 0:
            if scene.get("pipeline_status", "") == "done":
                print("🧪 Starte Markerprüfung…")
                self._step = 1
            return {'PASS_THROUGH'}

        # Step 1: Low-Marker-Check → ggf. neuer Zyklus, sonst direkt Solve
        if self._step == 1:
            space = getattr(context, "space_data", None)
            clip = getattr(space, "clip", None)
            if clip is None or not getattr(clip, "tracking", None):
                self.report({'WARNING'}, "Kein gültiger Clip oder keine Tracking-Daten.")
                return {'CANCELLED'}

            initial_basis = int(scene.get("marker_basis", 25))
            marker_basis = int(scene.get("marker_basis", 25))
            repeat_collection = scene.repeat_frame

            frame = find_low_marker_frame(clip, marker_basis=marker_basis)
            if frame is not None:
                print(f"🟡 Zu wenige Marker im Frame {frame}")
                scene["goto_frame"] = int(frame)
                jump_to_frame(context)

                key = str(frame)
                entry = next((e for e in repeat_collection if e.frame == key), None)

                if entry:
                    entry.count += 1
                    marker_basis = min(int(marker_basis * 1.1), 100)
                    scene["marker_basis"] = marker_basis
                    print(f"🔺 Selber Frame erneut – erhöhe marker_basis auf {marker_basis}")
                else:
                    entry = repeat_collection.add()
                    entry.frame = key
                    entry.count = 1
                    marker_basis = max(int(marker_basis * 0.9), initial_basis)
                    scene["marker_basis"] = marker_basis
                    print(f"🔻 Neuer Frame – senke marker_basis auf {marker_basis}")

                print(f"🔁 Frame {frame} wurde bereits {entry.count}x erkannt.")

                # Marker-Zielwerte setzen (Bounded)
                basis_for_bounds = (
                    int(self.marker_adapt * 1.1)
                    if int(getattr(self, "marker_adapt", 0)) > 0
                    else int(marker_basis)
                )
                scene["marker_min"] = int(basis_for_bounds * 0.9)
                scene["marker_max"] = int(basis_for_bounds * 1.1)
                print(f"🔄 Neuer Tracking-Zyklus mit Marker-Zielwerten {scene['marker_min']}–{scene['marker_max']}")

                bpy.ops.clip.tracking_pipeline('INVOKE_DEFAULT')
                self._step = 0
                return {'PASS_THROUGH'}

            # ⛔ Kein Low-Marker-Frame mehr → direkt Solve, KEIN Cleanup
            print("🏁 Keine Low-Marker-Frames mehr gefunden. Starte Kamera-Solve und beende.")
            self._start_solve_in_clip_context(context)
            self._teardown(context, cancelled=False)
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    # --- Helpers ---
    def _start_solve_in_clip_context(self, context):
        """Solve im CLIP_EDITOR-Kontext starten."""
        area_ce = region_ce = space_ce = None
        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area_ce = a
                        region_ce = r
                        space_ce = a.spaces.active
        if area_ce and region_ce and space_ce:
            with context.temp_override(area=area_ce, region=region_ce, space_data=space_ce):
                bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')
        else:
            bpy.ops.clip.solve_watch_clean('INVOKE_DEFAULT')

    def _teardown(self, context, cancelled: bool):
        """Timer entfernen und Status zurücksetzen."""
        try:
            context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass

        scene = context.scene
        if cancelled:
            self.report({'WARNING'}, "Tracking-Setup manuell abgebrochen.")
        scene["pipeline_status"] = ""
        scene["marker_min"] = 0
        scene["marker_max"] = 0
        scene["goto_frame"] = -1
        if hasattr(scene, "repeat_frame"):
            scene.repeat_frame.clear()
        if cancelled:
            print("❌ Abbruch durch Benutzer – Setup zurückgesetzt.")
