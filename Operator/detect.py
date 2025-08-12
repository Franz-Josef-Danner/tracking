import bpy
import math
import time

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    factor = math.log10(threshold * 1e6) / 6
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=threshold,
    )

    # kein Listenmaterialisieren → gleicher Rückgabewert (int), weniger Overhead
    selected_count = sum(1 for t in tracking.tracks if t.select)
    return selected_count

def deselect_all_markers(tracking):
    for t in tracking.tracks:
        t.select = False

class CLIP_OT_detect(bpy.types.Operator):
    bl_idname = "clip.detect"
    bl_label = "Place Marker"
    bl_description = "Führt Marker-Platzierungs-Zyklus aus (Teil-Zyklus 1, max. 20 Versuche)"

    _timer = None

    @classmethod
    def poll(cls, context):
        return (
            context.area and
            context.area.type == "CLIP_EDITOR" and
            getattr(context.space_data, "clip", None)
        )

    def execute(self, context):
        scene = context.scene
        scene["detect_status"] = "pending"

        if scene.get("tracking_pipeline_active", False):
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.clip = getattr(context.space_data, "clip", None)
        if self.clip is None:
            scene["detect_status"] = "failed"
            return {'CANCELLED'}

        self.tracking = self.clip.tracking
        settings = self.tracking.settings

        self.detection_threshold = scene.get(
            "last_detection_threshold",
            getattr(settings, "default_correlation_min", 0.75),
        )
        self.marker_adapt = scene.get("marker_adapt", 20)
        self.max_marker = scene.get("max_marker", (self.marker_adapt * 1.1) + 1)
        self.min_marker = scene.get("min_marker", (self.marker_adapt * 0.9) - 1)

        image_width = self.clip.size[0]
        self.margin_base = int(image_width * 0.025)
        self.min_distance_base = int(image_width * 0.05)

        self.attempt = 0
        self.state = "DETECT"

        deselect_all_markers(self.tracking)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        scene = context.scene

        if self.state == "DETECT":
            if self.attempt == 0:
                deselect_all_markers(self.tracking)

            self.frame = scene.frame_current

            # Lookups cachen
            tracks = self.tracking.tracks
            self.width, self.height = self.clip.size
            w, h = self.width, self.height

            # existierende Marker-Positionen sammeln (korrekte API: Instanz-Methode)
            existing_positions = []
            for t in tracks:
                m = t.markers.find_frame(self.frame, exact=True)
                if m and not m.mute:
                    existing_positions.append((m.co[0] * w, m.co[1] * h))
            self.existing_positions = existing_positions

            # Basis für spätere Vergleiche
            self.initial_track_names = {t.name for t in tracks}
            self._len_before = len(tracks)

            perform_marker_detection(
                self.clip,
                self.tracking,
                self.detection_threshold,
                self.margin_base,
                self.min_distance_base,
            )

            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)


            self.wait_start = time.time()
            self.state = "WAIT"
            return {'PASS_THROUGH'}

        if self.state == "WAIT":
            tracks = self.tracking.tracks
            # billiger Längencheck zuerst; falls keine Änderung, Set-Bildung sparen
            if len(tracks) != getattr(self, "_len_before", len(tracks)) or (time.time() - self.wait_start) >= 3.0:
                current_names = {t.name for t in tracks}
                if current_names != self.initial_track_names or (time.time() - self.wait_start) >= 3.0:
                    self.state = "PROCESS"
            return {'PASS_THROUGH'}

        if self.state == "PROCESS":
            tracks = self.tracking.tracks
            w, h = self.width, self.height
            self.distance_px = int(self.width * 0.01)
            thr2 = float(self.distance_px) * float(self.distance_px)

            new_tracks = [t for t in tracks if t.name not in self.initial_track_names]

            # --- ENTFERNEN: Vorab-Selektion/Löschung von close_tracks (Liste existiert noch nicht) ---
            # for t in tracks:
            #     t.select = False
            # for t in close_tracks:
            #     t.select = True
            # if close_tracks:
            #     bpy.ops.clip.delete_track()
            # ------------------------------------------------------

            # close_tracks korrekt berechnen
            close_tracks = []
            existing = self.existing_positions
            for track in new_tracks:
                marker = track.markers.find_frame(self.frame, exact=True)
                if marker and not marker.mute:
                    x = marker.co[0] * w
                    y = marker.co[1] * h
                    # Quadratsummenvergleich (keine sqrt)
                    for ex, ey in existing:
                        dx = x - ex
                        dy = y - ey
                        if (dx * dx + dy * dy) < thr2:
                            close_tracks.append(track)
                            break

            # Selektion/Löschung erst jetzt – und nur wenn nötig
            if close_tracks:
                for t in tracks:
                    t.select = False
                for t in close_tracks:
                    t.select = True
                bpy.ops.clip.delete_track()

            close_set = set(close_tracks)
            cleaned_tracks = [t for t in new_tracks if t not in close_set]

            if cleaned_tracks:
                for t in tracks:
                    t.select = False
                for t in cleaned_tracks:
                    t.select = True

            anzahl_neu = len(cleaned_tracks)
            # ... Rest unverändert ...

            if anzahl_neu < self.min_marker or anzahl_neu > self.max_marker:
                for t in tracks:
                    t.select = False
                for t in cleaned_tracks:
                    t.select = True
                if cleaned_tracks:
                    bpy.ops.clip.delete_track()

                self.detection_threshold = max(
                    self.detection_threshold * ((anzahl_neu + 0.1) / self.marker_adapt),
                    0.0001,
                )
                scene["last_detection_threshold"] = self.detection_threshold

                self.attempt += 1
                if self.attempt >= 20:
                    scene["detect_status"] = "failed"
                    context.window_manager.event_timer_remove(self._timer)
                    return {'FINISHED'}

                self.state = "DETECT"
                return {'PASS_THROUGH'}

            else:
                scene["detect_status"] = "success"
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)

def register():
    bpy.utils.register_class(CLIP_OT_detect)

def unregister():
    bpy.utils.unregister_class(CLIP_OT_detect)

if __name__ == "__main__":
    register()
