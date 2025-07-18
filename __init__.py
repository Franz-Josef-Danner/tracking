bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 56),
    "blender": (4, 4, 0),
    "location": "View3D > Object",
    "description": "Zeigt eine einfache Meldung an",
    "category": "Object",
}

import bpy
import time
import os
import shutil
import math
from bpy.props import IntProperty, BoolProperty, FloatProperty

class OBJECT_OT_simple_operator(bpy.types.Operator):
    bl_idname = "object.simple_operator"
    bl_label = "Simple Operator"
    bl_description = "Gibt eine Meldung aus"

    def execute(self, context):
        self.report({'INFO'}, "Hello World from Addon")
        return {'FINISHED'}


class CLIP_OT_panel_button(bpy.types.Operator):
    bl_idname = "clip.panel_button"
    bl_label = "Proxy"
    bl_description = "Erstellt Proxy-Dateien mit 50% Gr\u00f6\u00dfe"

    def execute(self, context):
        clip = context.space_data.clip

        clip.use_proxy = True

        clip.proxy.build_25 = False
        clip.proxy.build_50 = True
        clip.proxy.build_75 = False
        clip.proxy.build_100 = False

        # Proxy mit Qualität 50 erzeugen
        clip.proxy.quality = 50

        clip.proxy.directory = "//proxies"

        # absoluten Pfad zum Proxy-Verzeichnis auflösen
        proxy_dir = bpy.path.abspath(clip.proxy.directory)
        project_dir = bpy.path.abspath("//")

        # nur löschen, wenn das Verzeichnis innerhalb des Projektes liegt
        if os.path.abspath(proxy_dir).startswith(os.path.abspath(project_dir)):
            if os.path.exists(proxy_dir):
                try:
                    shutil.rmtree(proxy_dir)
                except Exception as e:
                    self.report({'WARNING'}, f"Fehler beim L\u00f6schen des Proxy-Verzeichnisses: {e}")

        # Blender-Operator zum Erzeugen der Proxys aufrufen
        bpy.ops.clip.rebuild_proxy()

        self.report({'INFO'}, "Proxy auf 50% erstellt")
        return {'FINISHED'}


class CLIP_OT_detect_button(bpy.types.Operator):
    bl_idname = "clip.detect_button"
    bl_label = "Detect"
    bl_description = "Erkennt Features mit dynamischen Parametern"

    def execute(self, context):
        space = context.space_data
        clip = space.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = False

        width, height = clip.size
        print(f"Auflösung: {width} x {height}")

        mframe = context.scene.marker_frame
        track_plus = mframe * 4

        nm_current = sum(1 for t in clip.tracking.tracks if t.name.startswith("NEW_"))
        nm = context.scene.nm_count

        threshold_value = context.scene.threshold_value
        if nm >= 1:
            formula = f"{threshold_value} * (({nm} + 0.1) / {track_plus})"
            threshold_value = threshold_value * ((nm + 0.1) / track_plus)
            print(f"Formel angewendet: {formula} = {threshold_value:.3f}")
        else:
            threshold_value = 1.0
            print("Formel nicht angewendet, NM < 1")

        detection_threshold = max(min(threshold_value, 1.0), 0.0001)
        print(
            f"NEW_ Tracks aktuell: {nm_current}, NM: {nm}, track_plus: {track_plus:.2f}"
        )

        margin_base = int(width * 0.01)
        min_distance_base = int(width * 0.05)

        factor = math.log10(detection_threshold * 10000000000) / 10
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)
        factor_formula = f"log10({detection_threshold:.3f} * 10000000000) / 10"
        print(f"Faktor: {factor_formula} = {factor:.3f}")
        print(f"Margin: int({margin_base} * {factor:.3f}) = {margin}")
        print(
            f"Min Distance: int({min_distance_base} * {factor:.3f}) = {min_distance}"
        )

        active = None
        if hasattr(space, "tracking"):
            active = space.tracking.active_track
        if active:
            active.pattern_size = 50
            active.search_size = 100

        print(
            f"detect_features: threshold={detection_threshold:.3f}, margin={margin}, min_distance={min_distance}"
        )
        bpy.ops.clip.detect_features(
            threshold=detection_threshold,
            min_distance=min_distance,
            margin=margin,
        )
        context.scene.threshold_value = threshold_value
        return {'FINISHED'}


class CLIP_OT_prefix_new(bpy.types.Operator):
    bl_idname = "clip.prefix_new"
    bl_label = "NEW"
    bl_description = "Präfix NEW_ für selektierte Tracks setzen"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = "NEW_"
        count = 0
        for track in clip.tracking.tracks:
            if track.select and not track.name.startswith(prefix):
                track.name = prefix + track.name
                count += 1
        self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_distance_button(bpy.types.Operator):
    bl_idname = "clip.distance_button"
    bl_label = "Distance"
    bl_description = (
        "Markiert NEW_ Tracks, die zu nah an GOOD_ Tracks liegen und "
        "deselektiert alle anderen"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        frame = context.scene.frame_current
        width, height = clip.size
        min_distance_px = int(width * 0.002)

        # Alle Tracks zunächst deselektieren
        for t in clip.tracking.tracks:
            t.select = False

        new_tracks = [t for t in clip.tracking.tracks if t.name.startswith("NEW_")]
        good_tracks = [t for t in clip.tracking.tracks if t.name.startswith("GOOD_")]
        marked = 0
        for nt in new_tracks:
            nm = nt.markers.find_frame(frame)
            if not nm:
                continue
            nx = nm.co[0] * width
            ny = nm.co[1] * height
            for gt in good_tracks:
                gm = gt.markers.find_frame(frame)
                if not gm:
                    continue
                gx = gm.co[0] * width
                gy = gm.co[1] * height
                dist = math.hypot(nx - gx, ny - gy)
                if dist < min_distance_px:
                    nt.select = True
                    marked += 1
                    break
        self.report({'INFO'}, f"{marked} Tracks markiert")
        return {'FINISHED'}


class CLIP_OT_delete_selected(bpy.types.Operator):
    bl_idname = "clip.delete_selected"
    bl_label = "Delete"
    bl_description = "Löscht selektierte Tracks"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        has_selection = any(t.select for t in clip.tracking.tracks)
        if not has_selection:
            self.report({'WARNING'}, "Keine Tracks ausgewählt")
            return {'CANCELLED'}

        if bpy.ops.clip.delete_track.poll():
            bpy.ops.clip.delete_track()
            self.report({'INFO'}, "Tracks gelöscht")
        else:
            self.report({'WARNING'}, "Löschen nicht möglich")
        return {'FINISHED'}


class CLIP_OT_count_button(bpy.types.Operator):
    bl_idname = "clip.count_button"
    bl_label = "Count"
    bl_description = "Selektiert und zählt NEW_-Tracks"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = "NEW_"
        for t in clip.tracking.tracks:
            t.select = t.name.startswith(prefix)
        count = sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
        print(f"Anzahl der Tracking Marker mit Präfix '{prefix}': {count}")
        context.scene.nm_count = count
        print(f"NM-Wert: {context.scene.nm_count}")

        mframe = context.scene.marker_frame
        track_plus = mframe * 4
        track_min = track_plus * 0.8
        track_max = track_plus * 1.2

        if track_min <= count <= track_max:
            for t in clip.tracking.tracks:
                if t.name.startswith(prefix):
                    t.name = "TRACK_" + t.name[4:]
                    t.select = False
            context.scene.nm_count = 0
            print(f"NM-Wert: {context.scene.nm_count}")
            self.report({'INFO'}, f"{count} Tracks in TRACK_ umbenannt")
        else:
            self.report({'INFO'}, f"{count} NEW_-Tracks ausserhalb des Bereichs")
        return {'FINISHED'}


class CLIP_OT_all_buttons(bpy.types.Operator):
    bl_idname = "clip.all_buttons"
    bl_label = "All"
    bl_description = (
        "Führt Detect, NEW, Distance, Delete, Count und Delete mehrfach aus"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        for _ in range(10):
            bpy.ops.clip.detect_button()
            bpy.ops.clip.prefix_new()
            bpy.ops.clip.distance_button()
            bpy.ops.clip.delete_selected()
            bpy.ops.clip.count_button()
            bpy.ops.clip.delete_selected()

            has_track = any(t.name.startswith("TRACK_") for t in clip.tracking.tracks)
            if has_track:
                break
        else:
            self.report({'WARNING'}, "Maximale Wiederholungen erreicht")

        return {'FINISHED'}


class CLIP_OT_track_sequence(bpy.types.Operator):
    bl_idname = "clip.track_sequence"
    bl_label = "Track"
    bl_description = (
        "Verfolgt TRACK_-Marker in dynamischen Bl\xF6cken r\xFCckw\xE4rts und vorw\xE4rts"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren
        clip.use_proxy = True

        scene = context.scene

        original_start = scene.frame_start
        original_end = scene.frame_end

        current = scene.frame_current

        def count_active_tracks(frame_value):
            count = 0
            for t in clip.tracking.tracks:
                if t.name.startswith("TRACK_"):
                    m = t.markers.find_frame(frame_value)
                    if m and not m.mute and m.co.length_squared != 0.0:
                        count += 1
            return count

        for t in clip.tracking.tracks:
            t.select = t.name.startswith("TRACK_")

        selected = [t for t in clip.tracking.tracks if t.select]
        print(f"🔢 Selektierte Marker: {len(selected)}")

        if not selected:
            print("⚠️ Keine selektierten Marker zum Tracken.")
            return {'CANCELLED'}

        frame = current
        start_frame = original_start
        while frame >= start_frame:
            remaining = frame - start_frame
            block_size = max(1, math.ceil(remaining / 4))
            limited_start = max(start_frame, frame - block_size)
            scene.frame_start = limited_start
            scene.frame_end = frame
            print(
                f"🔁 R\xFCckw\xE4rts-Tracking von {frame} bis {limited_start} (Blockgr\xF6\xDFe: {block_size})"
            )
            bpy.ops.clip.track_markers(backwards=True, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_start)
            print(f"📈 Aktive Marker: {active_count}")
            if active_count == 0:
                print(
                    "✅ Keine aktiven TRACK_-Marker mehr vorhanden. Tracking gestoppt."
                )
                break
            frame = limited_start - 1

        frame = current
        end_frame = original_end
        while frame <= end_frame:
            remaining = end_frame - frame
            block_size = max(1, math.ceil(remaining / 4))
            limited_end = min(frame + block_size, end_frame)
            scene.frame_start = frame
            scene.frame_end = limited_end
            print(
                f"🔁 Vorw\xE4rts-Tracking von {frame} bis {limited_end} (Blockgr\xF6\xDFe: {block_size})"
            )
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_end)
            print(f"📈 Aktive Marker: {active_count}")
            if active_count == 0:
                print("✅ Keine aktiven TRACK_-Marker mehr vorhanden. Tracking gestoppt.")
                break
            frame = limited_end + 1

        scene.frame_start = original_start
        scene.frame_end = original_end

        return {'FINISHED'}


def has_active_marker(tracks, frame):
    for t in tracks:
        m = t.markers.find_frame(frame)
        if m and not m.mute and m.co.length_squared != 0.0:
            return True
    return False


class CLIP_OT_live_track_forward(bpy.types.Operator):
    """Starte UI-Tracking vorw\u00e4rts und \u00fcberpr\u00fcfe aktive Marker"""

    bl_idname = "clip.live_track_forward"
    bl_label = "UI Live Track Forward"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _last_checked_frame = None
    _tracks = []

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'TIMER':
            current_frame = scene.frame_current
            if current_frame == self._last_checked_frame:
                self.report({'INFO'}, "Tracking abgeschlossen.")
                return self.finish(context)
            self._last_checked_frame = current_frame
            if not has_active_marker(self._tracks, current_frame):
                self.report(
                    {'INFO'},
                    f"Tracking gestoppt: Keine aktiven TRACK_-Marker bei Frame {current_frame}",
                )
                return self.finish(context)
        return {'PASS_THROUGH'}

    def execute(self, context):
        clip = context.space_data.clip
        scene = context.scene
        self._tracks = [t for t in clip.tracking.tracks if t.name.startswith('TRACK_')]
        if not self._tracks:
            self.report({'WARNING'}, "Keine TRACK_-Marker gefunden.")
            return {'CANCELLED'}
        self._last_checked_frame = scene.frame_current
        bpy.ops.clip.track_markers(backwards=False, sequence=True)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        return {'FINISHED'}


class CLIP_OT_live_track_backward(bpy.types.Operator):
    """Starte UI-Tracking r\u00fcckw\u00e4rts und \u00fcberpr\u00fcfe aktive Marker"""

    bl_idname = "clip.live_track_backward"
    bl_label = "UI Live Track Backward"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _last_checked_frame = None
    _tracks = []

    def modal(self, context, event):
        scene = context.scene
        if event.type == 'TIMER':
            current_frame = scene.frame_current
            if current_frame == self._last_checked_frame:
                self.report({'INFO'}, "R\u00fcckw\u00e4rts-Tracking abgeschlossen.")
                return self.finish(context)
            self._last_checked_frame = current_frame
            if not has_active_marker(self._tracks, current_frame):
                self.report(
                    {'INFO'},
                    f"Tracking gestoppt: Keine aktiven TRACK_-Marker bei Frame {current_frame}",
                )
                return self.finish(context)
        return {'PASS_THROUGH'}

    def execute(self, context):
        clip = context.space_data.clip
        scene = context.scene
        self._tracks = [t for t in clip.tracking.tracks if t.name.startswith('TRACK_')]
        if not self._tracks:
            self.report({'WARNING'}, "Keine TRACK_-Marker gefunden.")
            return {'CANCELLED'}
        self._last_checked_frame = scene.frame_current
        bpy.ops.clip.track_markers(backwards=True, sequence=True)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.2, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        return {'FINISHED'}


class CLIP_OT_proxy_track(bpy.types.Operator):
    """Proxy aktivieren und Marker vor- und zurückverfolgen"""

    bl_idname = "clip.proxy_track"
    bl_label = "Proxy Track"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren
        clip.use_proxy = True

        # Aktuellen Frame merken
        scene = context.scene
        saved_frame = scene.frame_current

        # TRACK_-Marker auswählen
        for t in clip.tracking.tracks:
            t.select = t.name.startswith("TRACK_")


        original_start = scene.frame_start
        original_end = scene.frame_end

        def count_active_tracks(frame_value):
            count = 0
            for tr in clip.tracking.tracks:
                if tr.name.startswith("TRACK_"):
                    m = tr.markers.find_frame(frame_value)
                    if m and not m.mute and m.co.length_squared != 0.0:
                        count += 1
            return count

        frame = saved_frame
        start_frame = original_start
        while frame >= start_frame:
            remaining = frame - start_frame
            block_size = max(1, math.ceil(remaining / 4))
            limited_start = max(start_frame, frame - block_size)
            scene.frame_start = limited_start
            scene.frame_end = frame
            print(
                f"\U0001F501 R\u00fcckw\u00e4rts-Tracking von {frame} bis {limited_start} (Blockgr\u00f6\u00dfe: {block_size})"
            )
            bpy.ops.clip.track_markers(backwards=True, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active = count_active_tracks(limited_start)
            print(f"\U0001F4C8 Aktive Marker: {active}")
            if active == 0:
                print("✅ Keine aktiven TRACK_-Marker mehr vorhanden. Tracking gestoppt.")
                break
            frame = limited_start - 1

        scene.frame_start = saved_frame
        scene.frame_end = original_end
        scene.frame_current = saved_frame
        print(f"\U0001F501 Vorw\u00e4rts-Tracking von {saved_frame} bis {original_end}")
        bpy.ops.clip.track_markers(backwards=False, sequence=True)

        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_current = saved_frame

        return {'FINISHED'}




class CLIP_PT_tracking_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Track'
    bl_label = 'Addon Panel'

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon Informationen")


class CLIP_PT_button_panel(bpy.types.Panel):
    bl_space_type = 'CLIP_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Addon'
    bl_label = 'Button Panel'

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'marker_frame', text='Marker / Frame')
        layout.operator('clip.panel_button')
        layout.operator('clip.proxy_track', text='Proxy+Track')
        layout.operator('clip.all_buttons', text='All')
        layout.operator('clip.track_sequence', text='Track')
        layout.operator('clip.live_track_forward', text='Live Fwd')
        layout.operator('clip.live_track_backward', text='Live Back')

classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_OT_detect_button,
    CLIP_OT_prefix_new,
    CLIP_OT_distance_button,
    CLIP_OT_delete_selected,
    CLIP_OT_count_button,
    CLIP_OT_all_buttons,
    CLIP_OT_track_sequence,
    CLIP_OT_proxy_track,
    CLIP_OT_live_track_forward,
    CLIP_OT_live_track_backward,
    CLIP_PT_tracking_panel,
    CLIP_PT_button_panel,
)


def register():
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker / Frame",
        description="Frame f\u00fcr neuen Marker",
        default=20,
    )
    bpy.types.Scene.nm_count = IntProperty(
        name="NM",
        description="Anzahl der NEW_-Tracks nach Count",
        default=0,
    )
    bpy.types.Scene.threshold_value = FloatProperty(
        name="Threshold Value",
        description="Gespeicherter Threshold-Wert",
        default=1.0,
    )
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    if hasattr(bpy.types.Scene, "marker_frame"):
        del bpy.types.Scene.marker_frame
    if hasattr(bpy.types.Scene, "nm_count"):
        del bpy.types.Scene.nm_count
    if hasattr(bpy.types.Scene, "threshold_value"):
        del bpy.types.Scene.threshold_value

if __name__ == "__main__":
    register()
