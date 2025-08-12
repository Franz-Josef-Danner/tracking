import bpy
import math
import time
from mathutils.kdtree import KDTree  # für O(log N) Nachbarsuche

def perform_marker_detection(clip, tracking, threshold, margin_base, min_distance_base):
    factor = math.log10(threshold * 1e7) / 7
    margin = max(1, int(margin_base * factor))
    min_distance = max(1, int(min_distance_base * factor))

    bpy.ops.clip.detect_features(
        margin=margin,
        min_distance=min_distance,
        threshold=threshold,
    )

    # Interface unverändert belassen
    selected_tracks = [t for t in tracking.tracks if t.select]
    return len(selected_tracks)

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
        # Tick seltener → weniger Overhead
        self._timer = wm.event_timer_add(0.03, window=context.window)
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
            self.width, self.height = self.clip.size
            self.distance_px = int(self.width * 0.04)

            tracks = self.tracking.tracks
            w, h = self.width, self.height

            # existierende Marker-Positionen (Frame-exakt) sammeln
            self.existing_positions = []
            for t in tracks:
                m = t.markers.find_frame(self.frame, exact=True)
                if m and not m.mute:
                    self.existing_positions.append((m.co[0] * w, m.co[1] * h))

            # robuste „Vorher“-Signatur: IDs statt Namen
            self._len_before = len(tracks)
            self._ids_before = {id(t) for t in tracks}
            self.initial_track_names = {t.name for t in tracks}  # Oberfläche unverändert lassen

            # Detection ausführen
            perform_marker_detection(
                self.clip,
                self.tracking,
                self.detection_threshold,
                self.margin_base,
                self.min_distance_base,
            )

            self.wait_start = time.time()
            self.state = "WAIT"
            return {'PASS_THROUGH'}

        if self.state == "WAIT":
            # Schnellpfad: Längenänderung als Signal; Fallback: Namen
            if (
                len(self.tracking.tracks) != self._len_before
                or time.time() - self.wait_start >= 1.5  # kürzeres Timeout
                or {t.name for t in self.tracking.tracks} != self.initial_track_names
            ):
                self.state = "PROCESS"
            return {'PASS_THROUGH'}

        if self.state == "PROCESS":
            tracks = self.tracking.tracks
            w, h = self.width, self.height

            # neue Tracks via ID-Differenz (robust, O(n))
            new_tracks = [t for t in tracks if id(t) not in self._ids_before]

            # KDTree über bestehende Positionen
            thr = float(self.distance_px)
            kd = None
            if self.existing_positions:
                kd = KDTree(len(self.existing_positions))
                for i, (ex, ey) in enumerate(self.existing_positions):
                    kd.insert((ex, ey, 0.0), i)
                kd.balance()

            # Nähe-Test über KDTree (oder Fallback auf nix)
            to_delete = []
            if kd is not None:
                find = kd.find
                for tr in new_tracks:
                    m = tr.markers.find_frame(self.frame, exact=True)
                    if not (m and not m.mute):
                        continue
                    x = m.co[0] * w
                    y = m.co[1] * h
                    _, _, dist = find((x, y, 0.0))
                    if dist < thr:
                        to_delete.append(tr)
            else:
                # keine bestehenden Marker → nichts filtern
                pass

            # direkte Removals statt bpy.ops (massiv billiger)
            if to_delete:
                for tr in to_delete:
                    tracks.remove(tr)

            # bereinigt = neu minus nahe
            # (Set-Vergleich auf IDs verhindert Name-Kollisionen)
            del_ids = {id(t) for t in to_delete}
            cleaned_tracks = [t for t in new_tracks if id(t) not in del_ids]

            # finale Selektion wie zuvor (Oberflächenverhalten beibehalten)
            for t in tracks:
                t.select = False
            for t in cleaned_tracks:
                t.select = True

            anzahl_neu = len(cleaned_tracks)

            if anzahl_neu < self.min_marker or anzahl_neu > self.max_marker:
                # statt Selektion+Operator: direkte Löschung der bereinigten neuen Marker
                if cleaned_tracks:
                    for tr in cleaned_tracks:
                        if tr in tracks:
                            tracks.remove(tr)

                ratio = (anzahl_neu + 0.1) / self.marker_adapt
                # Clamping vermeidet Oszillation → weniger Re-Tries
                if ratio < 0.5:
                    ratio = 0.5
                elif ratio > 1.5:
                    ratio = 1.5

                self.detection_threshold = max(self.detection_threshold * ratio, 0.0001)
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
