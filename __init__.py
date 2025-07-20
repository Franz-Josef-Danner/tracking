bl_info = {
    "name": "Simple Addon",
    "author": "Your Name",
    "version": (1, 90),
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
from bpy.props import IntProperty, FloatProperty

# Frames, die mit zu wenig Markern gefunden wurden
NF = []

# Marker count of the previous detection run
LAST_DETECT_COUNT = None

# Standard Motion Model
DEFAULT_MOTION_MODEL = 'Loc'
MOTION_MODELS = [
    'Loc',
    'LocRot',
    'LocScale',
    'LocRotScale',
    'Affine',
    'Perspective',
]

# Urspr\u00fcnglicher Wert f\u00fcr "Marker / Frame"
DEFAULT_MARKER_FRAME = 20

# Minimaler Threshold-Wert f\u00fcr die Feature-Erkennung
MIN_THRESHOLD = 0.0001


def pattern_base(clip):
    """Return the default pattern size based on the clip width."""
    width, _ = clip.size
    return int(width / 100)


def pattern_limits(clip):
    """Return minimum and maximum pattern size for a clip."""
    base = pattern_base(clip)
    min_size = int(base / 3)
    max_size = int(base * 3)
    return min_size, max_size


def clamp_pattern_size(value, clip):
    min_size, max_size = pattern_limits(clip)
    return max(min(value, max_size), min_size)


def cycle_motion_model(settings, clip, reset_size=True):
    """Cycle to the next default motion model."""
    current = settings.default_motion_model
    try:
        index = MOTION_MODELS.index(current)
    except ValueError:
        index = -1
    next_model = MOTION_MODELS[(index + 1) % len(MOTION_MODELS)]
    settings.default_motion_model = next_model
    if reset_size:
        base = pattern_base(clip)
        settings.default_pattern_size = clamp_pattern_size(base, clip)
        settings.default_search_size = settings.default_pattern_size * 2

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

        global LAST_DETECT_COUNT
        start_tracks = len(clip.tracking.tracks)

        width, height = clip.size

        mframe = context.scene.marker_frame
        track_plus = mframe * 4

        nm = context.scene.nm_count

        threshold_value = context.scene.threshold_value
        formula = f"{threshold_value} * (({nm} + 0.1) / {track_plus})"
        threshold_value = threshold_value * ((nm + 0.1) / track_plus)
        # Threshold formula output removed to keep the console clean

        detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)

        margin_base = int(width * 0.01)
        min_distance_base = int(width * 0.05)

        factor = math.log10(detection_threshold * 10000000000) / 10
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)
        factor_formula = f"log10({detection_threshold:.3f} * 10000000000) / 10"

        active = None
        if hasattr(space, "tracking"):
            active = space.tracking.active_track
        if active:
            base = pattern_base(clip)
            active.pattern_size = clamp_pattern_size(base, clip)
            active.search_size = active.pattern_size * 2

        bpy.ops.clip.detect_features(
            threshold=detection_threshold,
            min_distance=min_distance,
            margin=margin,
        )
        end_count = len(clip.tracking.tracks)
        new_markers = end_count - start_tracks
        settings = clip.tracking.settings
        if (
            LAST_DETECT_COUNT is not None
            and new_markers == LAST_DETECT_COUNT
            and new_markers > 0
            and detection_threshold <= MIN_THRESHOLD
        ):
            settings.default_pattern_size = int(settings.default_pattern_size * 0.9)
            settings.default_pattern_size = clamp_pattern_size(
                settings.default_pattern_size, clip
            )
            settings.default_search_size = settings.default_pattern_size * 2
        LAST_DETECT_COUNT = new_markers
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
        context.scene.nm_count = count

        mframe = context.scene.marker_frame
        track_plus = mframe * 4
        track_min = track_plus * 0.8
        track_max = track_plus * 1.2

        if track_min <= count <= track_max:
            for t in clip.tracking.tracks:
                if t.name.startswith(prefix):
                    t.name = "TRACK_" + t.name[4:]
                    t.select = False
            self.report({'INFO'}, f"{count} Tracks in TRACK_ umbenannt")
        else:
            self.report({'INFO'}, f"{count} NEW_-Tracks ausserhalb des Bereichs")
        return {'FINISHED'}


class CLIP_OT_all_cycle(bpy.types.Operator):
    bl_idname = "clip.all_cycle"
    bl_label = "All Cycle"
    bl_description = (
        "Startet einen kombinierten Tracking-Zyklus ohne Proxy-Bau, der mit Esc abgebrochen werden kann"
    )

    _timer = None
    _state = "DETECT"
    _detect_attempts = 0

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.cancel(context)

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return self.cancel(context)

        if self._state == 'DETECT':
            bpy.ops.clip.detect_button()
            bpy.ops.clip.prefix_new()
            bpy.ops.clip.distance_button()
            bpy.ops.clip.delete_selected()
            bpy.ops.clip.count_button()
            bpy.ops.clip.delete_selected()
            self._detect_attempts += 1
            has_track = any(t.name.startswith("TRACK_") for t in clip.tracking.tracks)
            if has_track:
                self._detect_attempts = 0
                self._state = 'TRACK'
            elif self._detect_attempts >= 20:
                self.report({'WARNING'}, "Maximale Wiederholungen erreicht")
                return self.cancel(context)

        elif self._state == 'TRACK':
            bpy.ops.clip.track_sequence()
            self._state = 'CLEAN'

        elif self._state == 'CLEAN':
            bpy.ops.clip.tracking_length()
            self._state = 'JUMP'

        elif self._state == 'JUMP':
            frame = jump_to_first_frame_with_few_active_markers(
                min_required=context.scene.marker_frame
            )
            if frame is None:
                return self.cancel(context)
            context.scene.frame_current = frame
            self._state = 'DETECT'

        return {'PASS_THROUGH'}

    def execute(self, context):
        self._state = 'DETECT'
        self._detect_attempts = 0
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        return {'CANCELLED'}


class CLIP_OT_track_sequence(bpy.types.Operator):
    bl_idname = "clip.track_sequence"
    bl_label = "Track"
    bl_description = (
        "Verfolgt TRACK_-Marker r\xFCckw\xE4rts in gro\xDFen Bl\xF6cken und danach vorw\xE4rts"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren
        clip.use_proxy = True
        # Prepass und Normalize einschalten
        settings = clip.tracking.settings
        settings.use_default_brute = True
        settings.use_default_normalization = True

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
        selected_names = [t.name for t in selected]

        if not selected:
            return {'CANCELLED'}

        frame = current
        start_frame = original_start
        total_range = frame - start_frame
        if total_range > 1:
            block_size = int(total_range / math.log10(total_range * total_range))
            block_size = max(1, block_size)
        else:
            block_size = 1
        while frame >= start_frame:
            limited_start = max(start_frame, frame - block_size)
            scene.frame_start = limited_start
            scene.frame_end = frame
            bpy.ops.clip.track_markers(backwards=True, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_start)
            if active_count == 0:
                
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
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            scene.frame_start = original_start
            scene.frame_end = original_end
            active_count = count_active_tracks(limited_end)
            if active_count == 0:
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


def get_undertracked_markers(clip, min_frames=10):
    undertracked = []

    for track in clip.tracking.tracks:
        if not track.name.startswith("TRACK_"):
            continue

        tracked_frames = [
            m for m in track.markers
            if not m.mute and m.co.length_squared != 0.0
        ]

        if len(tracked_frames) < min_frames:
            undertracked.append((track.name, len(tracked_frames)))

    return undertracked


def select_tracks_by_names(clip, name_list):
    for track in clip.tracking.tracks:
        track.select = track.name in name_list


def jump_to_first_frame_with_few_active_markers(min_required=5):
    scene = bpy.context.scene
    clip = bpy.context.space_data.clip

    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.tracks:
            if track.name.startswith("GOOD_"):
                marker = track.markers.find_frame(frame)
                if marker and not marker.mute and marker.co.length_squared != 0.0:
                    count += 1

        if count < min_required:
            scene.frame_current = frame
            _update_nf_and_motion_model(frame, clip)
            return frame

    return None


def _update_nf_and_motion_model(frame, clip):
    """Maintain NF list and adjust motion model and pattern size.

    Wenn die Pattern Size 100 erreicht, wird stattdessen der Wert aus
    ``Scene.marker_frame`` um 10 % erh\u00f6ht (maximal das Doppelte des
    Ausgangswerts). Sinkt die Pattern Size wieder unter 100, verkleinert sich
    ``marker_frame`` schrittweise um 10 %, bis der Startwert erreicht ist.
    """

    global NF
    settings = clip.tracking.settings
    scene = bpy.context.scene
    min_size, max_size = pattern_limits(clip)
    if frame in NF:
        cycle_motion_model(settings, clip, reset_size=False)
        if settings.default_pattern_size < max_size:
            settings.default_pattern_size = min(
                int(settings.default_pattern_size * 1.1),
                max_size,
            )
        else:
            max_mf = DEFAULT_MARKER_FRAME * 2
            scene.marker_frame = min(int(scene.marker_frame * 1.1), max_mf)
    else:
        NF.append(frame)
        settings.default_motion_model = DEFAULT_MOTION_MODEL
        settings.default_pattern_size = int(settings.default_pattern_size * 0.9)
        if settings.default_pattern_size < max_size and scene.marker_frame > DEFAULT_MARKER_FRAME:
            scene.marker_frame = max(int(scene.marker_frame * 0.9), DEFAULT_MARKER_FRAME)
    settings.default_pattern_size = clamp_pattern_size(settings.default_pattern_size, clip)
    settings.default_search_size = settings.default_pattern_size * 2
    print(f"NF frames: {NF}")


class CLIP_OT_tracking_length(bpy.types.Operator):
    bl_idname = "clip.tracking_length"
    bl_label = "Tracking Length"
    bl_description = (
        "Löscht TRACK_-Marker, deren Länge unter 'Frames/Track' liegt"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        min_frames = context.scene.frames_track
        undertracked = get_undertracked_markers(clip, min_frames=min_frames)

        if not undertracked:
            self.report({'INFO'}, "Alle TRACK_-Marker erreichen die gewünschte Länge")
            return {'FINISHED'}

        names = [name for name, _ in undertracked]
        select_tracks_by_names(clip, names)

        if bpy.ops.clip.delete_track.poll():
            bpy.ops.clip.delete_track()
            self.report({'INFO'}, f"{len(names)} TRACK_-Marker gelöscht")
        else:
            self.report({'WARNING'}, "Löschen nicht möglich")

        remaining = [t for t in clip.tracking.tracks if t.name.startswith("TRACK_")]
        select_tracks_by_names(clip, [t.name for t in remaining])
        for t in remaining:
            t.name = "GOOD_" + t.name[6:]

        for t in clip.tracking.tracks:
            t.select = False

        return {'FINISHED'}


class CLIP_OT_playhead_to_frame(bpy.types.Operator):
    bl_idname = "clip.playhead_to_frame"
    bl_label = "Playhead to Frame"
    bl_description = (
        "Springt zum ersten Frame, in dem weniger GOOD_-Marker aktiv sind als 'Marker / Frame' vorgibt"
    )

    def execute(self, context):
        min_required = context.scene.marker_frame
        jump_to_first_frame_with_few_active_markers(min_required=min_required)
        return {'FINISHED'}


class CLIP_OT_setup_defaults(bpy.types.Operator):
    bl_idname = "clip.setup_defaults"
    bl_label = "Defaults"
    bl_description = (
        "Setzt Tracking-Standards: Pattern 10, Motion Loc, Keyframe-Match"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = 10
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True

        # Mindestkorrelation und Margin für neue Tracks setzen
        settings.default_correlation_min = 0.85
        settings.default_margin = 10

        print(
            "Defaults gesetzt: "
            f"pattern_size={settings.default_pattern_size}, "
            f"search_size={settings.default_search_size}, "
            f"motion_model={settings.default_motion_model}, "
            f"pattern_match={settings.default_pattern_match}, "
            f"prepass={settings.use_default_brute}, "
            f"normalize={settings.use_default_normalization}, "
            f"channels=("
            f"{settings.use_default_red_channel}, "
            f"{settings.use_default_green_channel}, "
            f"{settings.use_default_blue_channel}), "
            f"correlation_min={settings.default_correlation_min}, "
            f"margin={settings.default_margin}"
        )

        bpy.ops.clip.detect_features()

        self.report({'INFO'}, "Tracking-Defaults gesetzt")
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
        layout.prop(context.scene, 'frames_track', text='Frames/Track')
        layout.operator('clip.panel_button')
        layout.operator('clip.setup_defaults', text='Defaults')
        layout.operator('clip.all_cycle', text='All Cycle')

classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_OT_detect_button,
    CLIP_OT_prefix_new,
    CLIP_OT_distance_button,
    CLIP_OT_delete_selected,
    CLIP_OT_count_button,
    CLIP_OT_setup_defaults,
    CLIP_OT_all_cycle,
    CLIP_OT_track_sequence,
    CLIP_OT_tracking_length,
    CLIP_OT_playhead_to_frame,
    CLIP_PT_tracking_panel,
    CLIP_PT_button_panel,
)


def register():
    bpy.types.Scene.marker_frame = IntProperty(
        name="Marker / Frame",
        description="Frame f\u00fcr neuen Marker",
        default=20,
    )
    bpy.types.Scene.frames_track = IntProperty(
        name="Frames/Track",
        description="Anzahl der Frames pro Tracking-Schritt",
        default=25,
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
    if hasattr(bpy.types.Scene, "frames_track"):
        del bpy.types.Scene.frames_track
    if hasattr(bpy.types.Scene, "nm_count"):
        del bpy.types.Scene.nm_count
    if hasattr(bpy.types.Scene, "threshold_value"):
        del bpy.types.Scene.threshold_value

if __name__ == "__main__":
    register()
