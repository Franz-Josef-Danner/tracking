
import bpy
import os
import shutil
import math
import re
from bpy.props import IntProperty, FloatProperty, BoolProperty

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

# Channel combinations for Test Detect CH
CHANNEL_COMBOS = [
    (True, False, False),
    (True, True, False),
    (True, True, True),
    (False, True, False),
    (False, True, True),
    (False, False, True),
]

# Urspr\u00fcnglicher Wert f\u00fcr "Marker/Frame"
DEFAULT_MARKER_FRAME = 20

# Minimaler Threshold-Wert f\u00fcr die Feature-Erkennung
MIN_THRESHOLD = 0.0001

# Zeitintervall für Timer-Operationen in Sekunden
TIMER_INTERVAL = 0.2

# Tracks that should be renamed after processing
PENDING_RENAME = []

# Test-Operator Ergebnisse
TEST_START_FRAME = None
TEST_END_FRAME = None
TEST_SETTINGS = {}
# Anzahl der zuletzt getrackten Frames
TRACKED_FRAMES = 0
# Letztes End-Frame-Ergebnis aus Track Full
LAST_TRACK_END = None


def add_timer(window_manager, window):
    """Create a timer using the global `TIMER_INTERVAL`."""
    return window_manager.event_timer_add(TIMER_INTERVAL, window=window)


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


def strip_prefix(name):
    """Remove an existing uppercase prefix from a track name."""
    return re.sub(r'^[A-Z]+_', '', name)


def add_pending_tracks(tracks):
    """Store new tracks for later renaming."""
    for t in tracks:
        if t not in PENDING_RENAME:
            PENDING_RENAME.append(t)


def clean_pending_tracks(clip):
    """Remove deleted tracks from the pending list."""
    names = {t.name for t in clip.tracking.tracks}
    remaining = [t for t in PENDING_RENAME if t.name in names]
    PENDING_RENAME.clear()
    PENDING_RENAME.extend(remaining)


def rename_pending_tracks(clip):
    """Rename pending tracks sequentially and clear the list."""
    clean_pending_tracks(clip)
    if not PENDING_RENAME:
        return
    existing_numbers = []
    for t in clip.tracking.tracks:
        m = re.search(r"(\d+)$", t.name)
        if m:
            existing_numbers.append(int(m.group(1)))
    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    for t in PENDING_RENAME:
        base = strip_prefix(t.name)
        t.name = f"Track {next_num:03d}"
        next_num += 1
    PENDING_RENAME.clear()


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


class CLIP_OT_proxy_on(bpy.types.Operator):
    bl_idname = "clip.proxy_on"
    bl_label = "Proxy on"
    bl_description = "Aktiviert das Proxy"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = True
        self.report({'INFO'}, "Proxy aktiviert")
        return {'FINISHED'}


class CLIP_OT_proxy_off(bpy.types.Operator):
    bl_idname = "clip.proxy_off"
    bl_label = "Proxy off"
    bl_description = "Deaktiviert das Proxy"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = False
        self.report({'INFO'}, "Proxy deaktiviert")
        return {'FINISHED'}


class CLIP_OT_track_nr1(bpy.types.Operator):
    bl_idname = "clip.track_nr1"
    bl_label = "Track Nr. 1"
    bl_options = {'REGISTER', 'UNDO'}

    _timer = None
    _state = "INIT"
    _start = 0
    _end = 0
    _tracked = 0

    def step_init(self, context):
        """Set defaults and remember the start frame."""
        if bpy.ops.clip.api_defaults.poll():
            bpy.ops.clip.api_defaults()
        self._start = context.scene.frame_current
        return "DETECT"

    def step_detect(self, context):
        """Generate markers using Cycle Detect."""
        if bpy.ops.clip.cycle_detect.poll():
            bpy.ops.clip.cycle_detect()
        return "TRACK"

    def step_track(self, context):
        """Track markers backward and forward."""
        scene = context.scene
        self._start = scene.frame_current
        if bpy.ops.clip.track_partial.poll():
            bpy.ops.clip.track_partial()
        self._end = scene.frame_current
        self._tracked = self._end - self._start
        print(
            f"[Track Nr.1] start {self._start} end {self._end} tracked {self._tracked}"
        )
        return "DECIDE"
    def step_decide(self, context):
        """Evaluate progress and continue or finish."""
        scene = context.scene
        print(
            f"[Track Nr.1] decide end {self._end} tracked {self._tracked} threshold {scene.frames_track}"
        )
        if self._tracked < scene.frames_track:
            print("[Track Nr.1] stop cycle: progress below threshold")
            return "RENAME"
        scene.frame_current = min(
            self._end + scene.frames_track, scene.frame_end
        )
        print(f"[Track Nr.1] next frame {scene.frame_current}")
        return "DETECT"

    def step_rename(self, context):
        if bpy.ops.clip.prefix_track.poll():
            bpy.ops.clip.prefix_track()
        return None

    def execute(self, context):
        wm = context.window_manager
        self._timer = add_timer(wm, context.window)
        self._state = "INIT"
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        return {'CANCELLED'}

    def modal(self, context, event):
        if event.type == 'ESC':
            return self.cancel(context)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        step_method = getattr(self, f"step_{self._state.lower()}", None)
        if step_method:
            next_state = step_method(context)
            if next_state is None:
                return self.cancel(context)
            self._state = next_state

        return {'RUNNING_MODAL'}


class CLIP_OT_detect_button(bpy.types.Operator):
    bl_idname = "clip.detect_button"
    bl_label = "Test Detect"
    bl_description = "Erkennt Features mit dynamischen Parametern"

    def execute(self, context):
        space = context.space_data
        clip = space.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = False

        global LAST_DETECT_COUNT

        width, _ = clip.size

        mframe = context.scene.marker_frame
        mf_base = mframe / 3

        threshold_value = 1.0

        detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)

        margin_base = int(width * 0.01)
        min_distance_base = int(width * 0.05)

        factor = math.log10(detection_threshold * 10000000000) / 10
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)


        active = None
        if hasattr(space, "tracking"):
            active = space.tracking.active_track
        if active:
            base = pattern_base(clip)
            active.pattern_size = clamp_pattern_size(base, clip)
            active.search_size = active.pattern_size * 2

        mf_min = mf_base * 0.9
        mf_max = mf_base * 1.1
        attempt = 0
        new_markers = 0

        while True:
            names_before = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=detection_threshold,
                min_distance=min_distance,
                margin=margin,
            )
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            for track in clip.tracking.tracks:
                track.select = False
            new_markers = len(new_tracks)
            if mf_min <= new_markers <= mf_max or attempt >= 10:
                break
            # neu erkannte Marker wie beim Delete-Operator entfernen
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            if new_tracks and bpy.ops.clip.delete_track.poll():
                bpy.ops.clip.delete_track()
                clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False
            threshold_value = threshold_value * ((new_markers + 0.1) / mf_base)
            # adjust detection threshold dynamically
            detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
            factor = math.log10(detection_threshold * 10000000000) / 10
            margin = int(margin_base * factor)
            min_distance = int(min_distance_base * factor)
            attempt += 1

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
        context.scene.nm_count = new_markers
        # Keep newly detected tracks selected
        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        add_pending_tracks(new_tracks)
        self.report({'INFO'}, f"{new_markers} Marker nach {attempt+1} Durchläufen")
        return {'FINISHED'}


class CLIP_OT_prefix_new(bpy.types.Operator):
    bl_idname = "clip.prefix_new"
    bl_label = "NEW"
    bl_description = "Präfix NEW_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

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
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_test(bpy.types.Operator):
    bl_idname = "clip.prefix_test"
    bl_label = "Name Test"
    bl_description = "Präfix TEST_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = "TEST_"
        count = 0
        for track in clip.tracking.tracks:
            if track.select and not track.name.startswith(prefix):
                track.name = prefix + track.name
                count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_track(bpy.types.Operator):
    bl_idname = "clip.prefix_track"
    bl_label = "Name Track"
    bl_description = "Präfix TRACK_ für selektierte Tracks setzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = "TRACK_"
        count = 0
        for track in clip.tracking.tracks:
            if track.select:
                base_name = strip_prefix(track.name)
                new_name = prefix + base_name
                if track.name != new_name:
                    track.name = new_name
                    count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_prefix_good(bpy.types.Operator):
    bl_idname = "clip.prefix_good"
    bl_label = "Name GOOD"
    bl_description = "TRACK_ durch GOOD_ ersetzen"

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        count = 0
        for track in clip.tracking.tracks:
            if track.name.startswith("TRACK_"):
                track.name = "GOOD_" + track.name[6:]
                count += 1
        if not self.silent:
            self.report({'INFO'}, f"{count} Tracks umbenannt")
        return {'FINISHED'}


class CLIP_OT_distance_button(bpy.types.Operator):
    bl_idname = "clip.distance_button"
    bl_label = "Distance"
    bl_description = (
        "Markiert neu erkannte Tracks, die zu nah an GOOD_ Tracks liegen, "
        "und deselektiert alle anderen"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        frame = context.scene.frame_current
        width, height = clip.size
        min_distance_px = int(width * 0.002)

        clean_pending_tracks(clip)

        # Alle Tracks zunächst deselektieren
        for t in clip.tracking.tracks:
            t.select = False

        new_tracks = list(PENDING_RENAME)
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

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        has_selection = any(t.select for t in clip.tracking.tracks)
        if not has_selection:
            if not self.silent:
                self.report({'WARNING'}, "Keine Tracks ausgewählt")
            return {'CANCELLED'}

        if bpy.ops.clip.delete_track.poll():
            bpy.ops.clip.delete_track()
            clean_pending_tracks(clip)
            if not self.silent:
                self.report({'INFO'}, "Tracks gelöscht")
        else:
            if not self.silent:
                self.report({'WARNING'}, "Löschen nicht möglich")
        return {'FINISHED'}


def select_short_tracks(clip, min_frames):
    """Select TRACK_ markers shorter than ``min_frames`` and return count."""
    undertracked = get_undertracked_markers(clip, min_frames=min_frames)

    for t in clip.tracking.tracks:
        t.select = False

    if not undertracked:
        return 0

    names = [name for name, _ in undertracked]
    select_tracks_by_names(clip, names)
    return len(names)




class CLIP_OT_select_short_tracks(bpy.types.Operator):
    bl_idname = "clip.select_short_tracks"
    bl_label = "Select Short Tracks"
    bl_description = (
        "Selektiert TRACK_-Marker, deren Länge unter 'Frames/Track' liegt"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        min_frames = context.scene.frames_track
        count = select_short_tracks(clip, min_frames)

        if count == 0:
            self.report({'INFO'}, "Keine kurzen TRACK_-Marker gefunden")
        else:
            self.report({'INFO'}, f"{count} TRACK_-Marker ausgewählt")

        return {'FINISHED'}


class CLIP_OT_count_button(bpy.types.Operator):
    bl_idname = "clip.count_button"
    bl_label = "Count"
    bl_description = "Selektiert und zählt TEST_-Tracks"
    silent: BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        prefix = "TEST_"
        for t in clip.tracking.tracks:
            t.select = t.name.startswith(prefix)
        count = sum(1 for t in clip.tracking.tracks if t.name.startswith(prefix))
        context.scene.nm_count = count

        mframe = context.scene.marker_frame
        mf_base = mframe / 3
        track_min = mf_base * 0.8
        track_max = mf_base * 1.2

        if track_min <= count <= track_max:
            for t in clip.tracking.tracks:
                if t.name.startswith(prefix):
                    t.name = "TRACK_" + t.name[len(prefix):]
                    t.select = False
            if not self.silent:
                self.report({'INFO'}, f"{count} Tracks in TRACK_ umbenannt")
        else:
            if not self.silent:
                self.report({'INFO'}, f"{count} TEST_-Tracks ausserhalb des Bereichs")
        return {'FINISHED'}


class CLIP_OT_defaults_detect(bpy.types.Operator):
    bl_idname = "clip.defaults_detect"
    bl_label = "Test Detect"
    bl_description = (
        "Wiederholt Detect und Count, bis genug Marker vorhanden sind"
    )

    def execute(self, context):
        return _Test_detect(self, context, use_defaults=False)


class CLIP_OT_motion_detect(bpy.types.Operator):
    bl_idname = "clip.motion_detect"
    bl_label = "Test Detect MM"
    bl_description = (
        "F\u00fchrt Test Detect mit jedem Motion Model aus und speichert das beste Ergebnis"
    )

    def execute(self, context):
        global TEST_END_FRAME, TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        original_model = settings.default_motion_model

        best_end = TEST_END_FRAME
        best_model = original_model

        # Apply stored defaults once
        settings.default_pattern_size = TEST_SETTINGS.get(
            "pattern_size", settings.default_pattern_size
        )
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_pattern_match = TEST_SETTINGS.get(
            "pattern_match", settings.default_pattern_match
        )
        r, g, b = TEST_SETTINGS.get("channels_active", (True, True, True))
        settings.use_default_red_channel = r
        settings.use_default_green_channel = g
        settings.use_default_blue_channel = b

        for model in MOTION_MODELS:
            settings.default_motion_model = model
            end_frame = _Test_detect_mm(self, context)
            if end_frame is None:
                continue
            self.report(
                {'INFO'},
                f"Run end_frame={end_frame}, pattern_size={settings.default_pattern_size}, "
                f"motion_model={model}, "
                f"channels=({settings.use_default_red_channel}, {settings.use_default_green_channel}, {settings.use_default_blue_channel})",
            )
            if best_end is None or end_frame > best_end:
                best_end = end_frame
                best_model = model

        settings.default_motion_model = best_model
        TEST_END_FRAME = best_end
        TEST_SETTINGS["motion_model"] = best_model

        self.report(
            {'INFO'},
            f"Test Detect MM best_end_frame={TEST_END_FRAME}, "
            f"pattern_size={TEST_SETTINGS.get('pattern_size')}, "
            f"motion_model={best_model}, "
            f"channels={TEST_SETTINGS.get('channels_active')}"
        )

        self.report({'INFO'}, "Test Detect MM abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_channel_detect(bpy.types.Operator):
    bl_idname = "clip.channel_detect"
    bl_label = "Test Detect CH"
    bl_description = (
        "F\u00fchrt Test Detect mit verschiedenen Farbkan\u00e4len aus und speichert das beste Ergebnis"
    )

    def execute(self, context):
        global TEST_END_FRAME, TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings

        best_end = TEST_END_FRAME
        best_channels = (
            settings.use_default_red_channel,
            settings.use_default_green_channel,
            settings.use_default_blue_channel,
        )

        # Apply stored defaults once
        settings.default_pattern_size = TEST_SETTINGS.get(
            "pattern_size", settings.default_pattern_size
        )
        settings.default_search_size = settings.default_pattern_size * 2
        settings.default_motion_model = TEST_SETTINGS.get(
            "motion_model", settings.default_motion_model
        )
        settings.default_pattern_match = TEST_SETTINGS.get(
            "pattern_match", settings.default_pattern_match
        )

        for channels in CHANNEL_COMBOS:
            (
                settings.use_default_red_channel,
                settings.use_default_green_channel,
                settings.use_default_blue_channel,
            ) = channels
            end_frame = _Test_detect_mm(self, context)
            if end_frame is None:
                continue
            self.report(
                {'INFO'},
                f"Run end_frame={end_frame}, pattern_size={settings.default_pattern_size}, "
                f"motion_model={settings.default_motion_model}, "
                f"channels={channels}",
            )
            if best_end is None or end_frame > best_end:
                best_end = end_frame
                best_channels = channels

        (
            settings.use_default_red_channel,
            settings.use_default_green_channel,
            settings.use_default_blue_channel,
        ) = best_channels
        TEST_END_FRAME = best_end
        TEST_SETTINGS["channels_active"] = best_channels

        self.report(
            {'INFO'},
            f"Test Detect CH best_end_frame={TEST_END_FRAME}, "
            f"pattern_size={TEST_SETTINGS.get('pattern_size')}, "
            f"motion_model={TEST_SETTINGS.get('motion_model')}, "
            f"channels={best_channels}"
        )

        self.report({'INFO'}, "Test Detect CH abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_apply_settings(bpy.types.Operator):
    bl_idname = "clip.apply_detect_settings"
    bl_label = "Test Detect Apply"
    bl_description = (
        "Setzt gespeicherte Test Detect Werte f\u00fcr Pattern, Motion Model und RGB"
        " Kan\u00e4le"
    )

    def execute(self, context):
        global TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not TEST_SETTINGS:
            self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
            return {'CANCELLED'}

        settings = clip.tracking.settings

        pattern_size = TEST_SETTINGS.get("pattern_size")
        if pattern_size is not None:
            settings.default_pattern_size = pattern_size
            settings.default_search_size = pattern_size * 2

        # Extras: Mindestkorrelation und Margin
        settings.default_correlation_min = 0.9
        settings.default_margin = settings.default_pattern_size * 2

        motion_model = TEST_SETTINGS.get("motion_model")
        if motion_model is not None:
            settings.default_motion_model = motion_model

        channels = TEST_SETTINGS.get("channels_active")
        if channels:
            r, g, b = channels
            settings.use_default_red_channel = r
            settings.use_default_green_channel = g
            settings.use_default_blue_channel = b

        self.report({'INFO'}, "Gespeicherte Test Detect Werte gesetzt")
        return {'FINISHED'}


class CLIP_OT_track_bidirectional(bpy.types.Operator):
    bl_idname = "clip.track_bidirectional"
    bl_label = "Track"
    bl_description = (
        "Trackt selektierte Marker r\u00fcckw\u00e4rts zum Szenenanfang und danach vorw\u00e4rts"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        if not any(t.select for t in clip.tracking.tracks):
            self.report({'WARNING'}, "Keine Tracks ausgew\u00e4hlt")
            return {'CANCELLED'}

        scene = context.scene
        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current


        if not bpy.ops.clip.track_markers.poll():
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")
            return {'CANCELLED'}

        scene.frame_start = original_start
        scene.frame_end = current
        bpy.ops.clip.track_markers(backwards=True, sequence=True)

        scene.frame_start = current
        scene.frame_end = original_end
        scene.frame_current = current
        bpy.ops.clip.track_markers(backwards=False, sequence=True)

        scene.frame_start = original_start
        scene.frame_end = original_end
        scene.frame_current = current


        return {'FINISHED'}


class CLIP_OT_track_partial(bpy.types.Operator):
    bl_idname = "clip.track_partial"
    bl_label = "Track Partial"
    bl_description = (
        "Trackt selektierte Marker r\u00fcckw\u00e4rts bis zum Szenenanfang "
        "und danach vorw\u00e4rts bis zum Szenenende"
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        for track in clip.tracking.tracks:
            if track.select:
                marker = track.markers.find_frame(scene.frame_current, exact=True)
                if marker is None or marker.mute:
                    track.select = False

        if not any(t.select for t in clip.tracking.tracks):
            self.report({'WARNING'}, "Keine g\u00fcltigen Marker ausgew\xe4hlt")
            return {'CANCELLED'}

        original_start = scene.frame_start
        original_end = scene.frame_end
        current = scene.frame_current

        print(
            f"[Track Partial] current {current} start {original_start} end {original_end}"
        )

        clip.use_proxy = True

        if bpy.ops.clip.track_markers.poll():
            print("[Track Partial] track backwards")
            scene.frame_start = original_start
            scene.frame_end = current
            bpy.ops.clip.track_markers(backwards=True, sequence=True)

            print("[Track Partial] track forwards")
            scene.frame_start = current
            scene.frame_end = original_end
            scene.frame_current = current
            bpy.ops.clip.track_markers(backwards=False, sequence=True)

        print(f"[Track Partial] done at frame {scene.frame_current}")

        scene.frame_start = original_start
        scene.frame_end = original_end

        return {'FINISHED'}

class CLIP_OT_all_detect(bpy.types.Operator):
    bl_idname = "clip.all_detect"
    bl_label = "Detect"
    bl_description = (
        "F\u00fchrt den Detect-Schritt aus All Cycle einzeln aus"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        width, _ = clip.size

        margin_base = int(width * 0.01)
        min_distance_base = int(width * 0.05)

        mfp = context.scene.marker_frame * 4
        mfp_min = mfp * 0.9
        mfp_max = mfp * 1.1

        threshold_value = 1.0
        detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
        factor = math.log10(detection_threshold * 10000000000) / 10
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)


        attempt = 0
        new_markers = 0
        while True:
            names_before = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=detection_threshold,
                min_distance=min_distance,
                margin=margin,
            )
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]

            new_markers = len(new_tracks)

            # Select new tracks for position logging
            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True

            # Output marker positions before validation
            if bpy.ops.clip.marker_position.poll():
                bpy.ops.clip.marker_position()
            if bpy.ops.clip.good_marker_position.poll():
                bpy.ops.clip.good_marker_position()

            # Compare coordinates with GOOD_ markers and mark nearby tracks
            frame = context.scene.frame_current
            width, height = clip.size
            # Use the computed min_distance as pixel radius
            distance_px = min_distance
            close_tracks = []
            good_positions = []
            for gt in clip.tracking.tracks:
                if not gt.name.startswith("GOOD_"):
                    continue
                gm = gt.markers.find_frame(frame, exact=True)
                if gm and not gm.mute:
                    good_positions.append((gm.co[0] * width, gm.co[1] * height))
            for nt in new_tracks:
                nm = nt.markers.find_frame(frame, exact=True)
                if nm and not nm.mute:
                    nx = nm.co[0] * width
                    ny = nm.co[1] * height
                    for gx, gy in good_positions:
                        if math.hypot(nx - gx, ny - gy) < distance_px:
                            close_tracks.append(nt)
                            break

            # Delete tracks that are too close to GOOD_ markers
            for track in clip.tracking.tracks:
                track.select = False
            for t in close_tracks:
                t.select = True
            if close_tracks and bpy.ops.clip.delete_selected.poll():
                bpy.ops.clip.delete_selected()
                clean_pending_tracks(clip)

            # Recompute new tracks after deletion
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]
            new_markers = len(new_tracks)

            # Clear selection again
            for track in clip.tracking.tracks:
                track.select = False

            if mfp_min <= new_markers <= mfp_max or attempt >= 10:
                break

            for track in clip.tracking.tracks:
                track.select = False
            for t in new_tracks:
                t.select = True
            if new_tracks and bpy.ops.clip.delete_track.poll():
                bpy.ops.clip.delete_track()
                clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False

            threshold_value = threshold_value * ((new_markers + 0.1) / mfp)
            detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
            factor = math.log10(detection_threshold * 10000000000) / 10
            margin = int(margin_base * factor)
            min_distance = int(min_distance_base * factor)
            attempt += 1

        context.scene.threshold_value = threshold_value
        context.scene.nm_count = new_markers

        # Keep newly detected tracks selected
        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        add_pending_tracks(new_tracks)

        return {'FINISHED'}


class CLIP_OT_cycle_detect(bpy.types.Operator):
    bl_idname = "clip.cycle_detect"
    bl_label = "Cycle Detect"
    bl_description = (
        "Wiederholt Detect Features bis zur Zielanzahl und pr\u00fcft den Abstand zu GOOD_- und TRACK_-Markern"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.use_proxy = False

        width, _ = clip.size

        margin_base = int(width * 0.01)
        min_distance_base = int(width * 0.05)

        target = context.scene.marker_frame * 4
        target_min = target * 0.9
        target_max = target * 1.1

        threshold_value = 1.0
        detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
        factor = math.log10(detection_threshold * 10000000000) / 10
        margin = int(margin_base * factor)
        min_distance = int(min_distance_base * factor)

        attempt = 0
        new_tracks = []
        while True:
            names_before = {t.name for t in clip.tracking.tracks}
            bpy.ops.clip.detect_features(
                threshold=detection_threshold,
                min_distance=min_distance,
                margin=margin,
            )
            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]

            frame = context.scene.frame_current
            width, height = clip.size
            distance_px = min_distance
            close_tracks = []
            valid_positions = []
            for gt in clip.tracking.tracks:
                if gt.name.startswith("GOOD_") or gt.name.startswith("TRACK_"):
                    gm = gt.markers.find_frame(frame, exact=True)
                    if gm and not gm.mute:
                        valid_positions.append((gm.co[0] * width, gm.co[1] * height))

            for nt in new_tracks:
                nm = nt.markers.find_frame(frame, exact=True)
                if nm and not nm.mute:
                    nx = nm.co[0] * width
                    ny = nm.co[1] * height
                    for vx, vy in valid_positions:
                        if math.hypot(nx - vx, ny - vy) < distance_px:
                            close_tracks.append(nt)
                            break

            for track in clip.tracking.tracks:
                track.select = False
            for t in close_tracks:
                t.select = True
            if close_tracks and bpy.ops.clip.delete_selected.poll():
                bpy.ops.clip.delete_selected()
                clean_pending_tracks(clip)

            names_after = {t.name for t in clip.tracking.tracks}
            new_tracks = [
                t for t in clip.tracking.tracks if t.name in names_after - names_before
            ]
            count = len(new_tracks)

            for track in clip.tracking.tracks:
                track.select = False

            if target_min <= count <= target_max or attempt >= 10:
                break

            for t in new_tracks:
                t.select = True
            if new_tracks and bpy.ops.clip.delete_track.poll():
                bpy.ops.clip.delete_track()
                clean_pending_tracks(clip)
            for track in clip.tracking.tracks:
                track.select = False

            threshold_value = threshold_value * ((count + 0.1) / target)
            detection_threshold = max(min(threshold_value, 1.0), MIN_THRESHOLD)
            factor = math.log10(detection_threshold * 10000000000) / 10
            margin = int(margin_base * factor)
            min_distance = int(min_distance_base * factor)
            attempt += 1

        for track in clip.tracking.tracks:
            track.select = False
        for t in new_tracks:
            t.select = True
        if new_tracks and bpy.ops.clip.prefix_new.poll():
            bpy.ops.clip.prefix_new(silent=True)
        add_pending_tracks(new_tracks)

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
            bpy.ops.clip.all_detect()
            bpy.ops.clip.distance_button()
            bpy.ops.clip.delete_selected()
            clean_pending_tracks(clip)

            count = len(PENDING_RENAME)
            mframe = context.scene.marker_frame
            mf_base = mframe * 4
            track_min = mf_base * 0.8
            track_max = mf_base * 1.2

            if track_min <= count <= track_max:
                for t in PENDING_RENAME:
                    t.select = True
                self._detect_attempts = 0
                self._state = 'TRACK'
            else:
                for t in PENDING_RENAME:
                    t.select = True
                bpy.ops.clip.delete_selected()
                clean_pending_tracks(clip)
                self._detect_attempts += 1
                if self._detect_attempts >= 20:
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
        self._timer = add_timer(wm, context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        clip = context.space_data.clip
        if clip:
            rename_pending_tracks(clip)
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
                if t.name.startswith("TRACK_") or t in PENDING_RENAME:
                    m = t.markers.find_frame(frame_value)
                    if m and not m.mute and m.co.length_squared != 0.0:
                        count += 1
            return count

        clean_pending_tracks(clip)
        for t in clip.tracking.tracks:
            t.select = t.name.startswith("TRACK_") or t in PENDING_RENAME

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

    clean_pending_tracks(clip)

    for track in clip.tracking.tracks:
        if not (track.name.startswith("TRACK_") or track in PENDING_RENAME):
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


def select_tracks_by_prefix(clip, prefix):
    """Select all tracks whose names start with the given prefix."""
    for track in clip.tracking.tracks:
        track.select = track.name.startswith(prefix)


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


def find_low_marker_frame(clip, threshold):
    """Return the first frame with fewer markers than ``threshold``."""
    scene = bpy.context.scene
    for frame in range(scene.frame_start, scene.frame_end + 1):
        count = 0
        for track in clip.tracking.tracks:
            marker = track.markers.find_frame(frame)
            if marker and not marker.mute and marker.co.length_squared != 0.0:
                count += 1
        if count < threshold:
            return frame, count
    return None, None


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

def _Test_detect(self, context, use_defaults=True):
    """Run the Test detect cycle optionally using default settings."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return {'CANCELLED'}

    mf_base = context.scene.marker_frame / 3
    mf_min = mf_base * 0.9
    mf_max = mf_base * 1.1

    if use_defaults:
        bpy.ops.clip.setup_defaults(silent=True)
    context.scene.threshold_value = 1.0

    # Begin Test detect cycle
    prev_best = TEST_END_FRAME
    last_end = None
    while True:
        for cycle in range(4):
            attempt = 0
            while True:
                # run detection for each attempt
                bpy.ops.clip.detect_button()
                count = sum(
                    1 for t in clip.tracking.tracks if t.name.startswith("TEST_")
                )
                context.scene.nm_count = count
                if mf_min <= count <= mf_max or attempt >= 10:
                    break
                for t in clip.tracking.tracks:
                    t.select = t.name.startswith("TEST_")
                if bpy.ops.clip.delete_track.poll():
                    bpy.ops.clip.delete_track()
                for t in clip.tracking.tracks:
                    t.select = False
                context.scene.threshold_value = 1.0
                attempt += 1

            if attempt >= 10 and not (mf_min <= count <= mf_max):
                self.report({'WARNING'}, "Maximale Wiederholungen erreicht")
                return {'CANCELLED'}

            select_tracks_by_prefix(clip, "TEST_")
            if bpy.ops.clip.track_full.poll():
                bpy.ops.clip.track_full(silent=True)
                last_end = LAST_TRACK_END
                s = clip.tracking.settings
                self.report(
                    {'INFO'},
                    f"Run end_frame={last_end}, pattern_size={s.default_pattern_size}, "
                    f"motion_model={s.default_motion_model}, "
                    f"channels=({s.use_default_red_channel}, {s.use_default_green_channel}, {s.use_default_blue_channel})",
                )
            else:
                self.report({'WARNING'}, "Tracking nicht möglich")

            select_tracks_by_prefix(clip, "TEST_")
            if bpy.ops.clip.delete_selected.poll():
                bpy.ops.clip.delete_selected(silent=True)
            if bpy.ops.clip.pattern_up.poll():
                bpy.ops.clip.pattern_up()
            for t in clip.tracking.tracks:
                t.select = False

        if prev_best is None or (last_end is not None and last_end > prev_best):
            prev_best = last_end
        elif last_end is not None and last_end < prev_best:
            break

    from_settings = TEST_SETTINGS or {}
    self.report(
        {'INFO'},
        f"Test Detect best_end_frame={TEST_END_FRAME}, "
        f"pattern_size={from_settings.get('pattern_size')}, "
        f"motion_model={from_settings.get('motion_model')}, "
        f"channels={from_settings.get('channels_active')}"
    )
    self.report({'INFO'}, f"{count} Marker gefunden")
    return {'FINISHED'}


def _Test_detect_mm(self, context):
    """Run a shortened Test detect cycle for motion-model tests."""
    clip = context.space_data.clip
    if not clip:
        self.report({'WARNING'}, "Kein Clip geladen")
        return None

    if not TEST_SETTINGS:
        self.report({'WARNING'}, "Keine gespeicherten Einstellungen")
        return None

    scene = context.scene

    start = TEST_START_FRAME if TEST_START_FRAME is not None else scene.frame_current

    best_end = None
    for cycle in range(4):
        scene.frame_current = start
        # run detect for each motion model cycle
        bpy.ops.clip.detect_button()

        select_tracks_by_prefix(clip, "TEST_")
        if bpy.ops.clip.track_markers.poll():
            # Proxy aktivieren für das Tracking
            clip.use_proxy = True
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
            end_frame = scene.frame_current
            if best_end is None or end_frame > best_end:
                best_end = end_frame
        else:
            self.report({'WARNING'}, "Tracking nicht möglich")
            break

        select_tracks_by_prefix(clip, "TEST_")
        if bpy.ops.clip.delete_selected.poll():
            bpy.ops.clip.delete_selected(silent=True)
        for t in clip.tracking.tracks:
            t.select = False

    scene.frame_current = start
    return best_end


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
        "Springt zum ersten Frame, in dem weniger GOOD_-Marker aktiv sind als 'Marker/Frame' vorgibt"
    )

    def execute(self, context):
        min_required = context.scene.marker_frame
        jump_to_first_frame_with_few_active_markers(min_required=min_required)
        return {'FINISHED'}


class CLIP_OT_low_marker_frame(bpy.types.Operator):
    bl_idname = "clip.low_marker_frame"
    bl_label = "Low Marker Frame"
    bl_description = (
        "Springt zum ersten Frame mit weniger Markern als 'Marker/Frame'"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        threshold = context.scene.marker_frame
        frame, count = find_low_marker_frame(clip, threshold)
        if frame is not None:
            context.scene.frame_current = frame
            self.report({'INFO'}, f"Frame {frame} hat nur {count} Marker")
        else:
            self.report({'INFO'}, "Kein Frame mit weniger Markern gefunden")

        return {'FINISHED'}


class CLIP_OT_select_active_tracks(bpy.types.Operator):
    bl_idname = "clip.select_active_tracks"
    bl_label = "Select TRACK"
    bl_description = (
        "Selektiert alle TRACK_-Marker ungeachtet ihres Status"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        select_tracks_by_prefix(clip, "TRACK_")

        frame = context.scene.frame_current

        for track in clip.tracking.tracks:
            if track.select:
                marker = track.markers.find_frame(frame, exact=True)
                if marker is None or marker.mute:
                    track.select = False

        count = sum(1 for t in clip.tracking.tracks if t.select)

        self.report({'INFO'}, f"{count} TRACK_-Marker ausgewählt")
        return {'FINISHED'}


class CLIP_OT_marker_position(bpy.types.Operator):
    bl_idname = "clip.marker_position"
    bl_label = "Marker Position"
    bl_description = (
        "Gibt die Pixelposition der Marker in selektierten Tracks im aktuellen Frame aus"
    )

    def get_selected_marker_positions_in_pixels(self, scene):
        frame = scene.frame_current
        clip = scene.active_clip

        if clip is None:
            raise RuntimeError("Kein aktiver Clip im Clip-Editor.")

        width, height = clip.size
        result = []

        for track in clip.tracking.tracks:
            if not track.select:
                continue

            marker = track.markers.find_frame(frame, exact=True)
            if marker is None or marker.mute:
                continue

            x_px = marker.co[0] * width
            y_px = marker.co[1] * height

            result.append(
                {
                    "track_name": track.name,
                    "frame": frame,
                    "x_px": x_px,
                    "y_px": y_px,
                }
            )

        return result

    def execute(self, context):
        try:
            markers = self.get_selected_marker_positions_in_pixels(context.scene)
        except RuntimeError as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}

        for m in markers:
            print(
                f"[{m['track_name']}] Frame {m['frame']}: "
                f"X={m['x_px']:.1f}px, Y={m['y_px']:.1f}px"
            )

        return {'FINISHED'}


class CLIP_OT_good_marker_position(bpy.types.Operator):
    bl_idname = "clip.good_marker_position"
    bl_label = "GOOD Marker Position"
    bl_description = (
        "Gibt die Pixelposition aller sichtbaren GOOD_-Marker im aktuellen Frame aus"
    )

    def execute(self, context):
        scene = context.scene
        frame = scene.frame_current
        clip = scene.active_clip

        if clip is None:
            self.report({'WARNING'}, "Kein aktiver Clip im Clip-Editor gefunden")
            return {'CANCELLED'}

        width, height = clip.size
        good_markers_px = []

        for track in clip.tracking.tracks:
            if not track.name.startswith("GOOD_"):
                continue

            marker = track.markers.find_frame(frame, exact=True)
            if marker is None or marker.mute:
                continue

            nx, ny = marker.co
            px, py = nx * width, ny * height

            good_markers_px.append({
                "track_name": track.name,
                "frame": frame,
                "x_px": px,
                "y_px": py,
            })

        for m in good_markers_px:
            print(
                f"[{m['track_name']} @ frame {m['frame']}] -> X: {m['x_px']:.1f} px, Y: {m['y_px']:.1f} px"
            )

        return {'FINISHED'}


class CLIP_OT_camera_solve(bpy.types.Operator):
    bl_idname = "clip.camera_solve"
    bl_label = "Kamera solve"
    bl_description = "Löst die Kamera anhand des aktuellen Clips"

    def execute(self, context):
        clip = context.space_data.clip
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        bpy.ops.clip.solve_camera()
        self.report({'INFO'}, "Camera solve complete.")
        return {'FINISHED'}


class CLIP_OT_track_cleanup(bpy.types.Operator):
    bl_idname = "clip.track_cleanup"
    bl_label = "Select Error Tracks"
    bl_description = (
        "Wählt TRACK_-Tracks aus, deren mittlere Position zu stark vom Gesamtmittel abweicht"
    )

    def execute(self, context):
        scene = context.scene
        clip = context.space_data.clip
        if clip is None:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        width, height = clip.size

        # Alle Marker abwählen
        for track in clip.tracking.tracks:
            track.select = False

        start = scene.frame_start + 1
        end = scene.frame_end

        g_global = scene.error_threshold * 6
        g_quarter = scene.error_threshold * 4
        g_eighth = scene.error_threshold * 2

        print(
            f"[Select Error Tracks] G_global = ET * 6 = {scene.error_threshold} * 6 = {g_global}"
        )
        print(
            f"[Select Error Tracks] G_quarter = ET * 4 = {scene.error_threshold} * 4 = {g_quarter}"
        )
        print(
            f"[Select Error Tracks] G_eighth = ET * 2 = {scene.error_threshold} * 2 = {g_eighth}"
        )

        selected_tracks = set()

        def analyze(tracks_info, g, label):
            if not tracks_info:
                return

            ava = sum(t["av"] for t in tracks_info) / len(tracks_info)
            print(
                f"[{label}] AVA = (Sum AV / AM) = ({sum(t['av'] for t in tracks_info):.3f} / {len(tracks_info)}) = {ava:.3f}"
            )

            for info in tracks_info:
                track = info["track"]
                av = info["av"]
                avx = info["avx"]
                avy = info["avy"]
                mxp1 = info["mxp1"]
                mxp2 = info["mxp2"]
                myp1 = info["myp1"]
                myp2 = info["myp2"]
                error_val = ava - av

                print(
                    f"[{label}] {track.name}: |MX1-MX2|={mxp1:.3f}, |MX2-MX3|={mxp2:.3f}, |MY1-MY2|={myp1:.3f}, |MY2-MY3|={myp2:.3f}, AVX=({mxp1:.3f}+{mxp2:.3f})/2={avx:.3f}, AVY=({myp1:.3f}+{myp2:.3f})/2={avy:.3f}, AV=({avx:.3f}+{avy:.3f})/2={av:.3f}; errorValue={ava:.3f}-{av:.3f}={error_val:.3f}"
                )

                if abs(error_val) > g:
                    print(
                        f"[{label}] {track.name} selected because |{error_val:.3f}| > G={g:.3f}"
                    )
                    track.select = True
                    selected_tracks.add(track)

        for frame in range(start, end):
            valid = []
            for track in clip.tracking.tracks:
                if not track.name.startswith("TRACK_"):
                    continue

                coords = []
                for f in (frame - 1, frame, frame + 1):
                    marker = track.markers.find_frame(f, exact=True)
                    if marker is None or marker.mute:
                        break
                    coords.append((marker.co[0] * width, marker.co[1] * height))

                if len(coords) == 3:
                    px1, py1 = coords[0]
                    px2, py2 = coords[1]
                    px3, py3 = coords[2]

                    mxp1 = abs(px1 - px2)
                    mxp2 = abs(px2 - px3)
                    myp1 = abs(py1 - py2)
                    myp2 = abs(py2 - py3)
                    avx = (mxp1 + mxp2) / 2.0
                    avy = (myp1 + myp2) / 2.0
                    av = (avx + avy) / 2.0
                    mx_mean = (px1 + px2 + px3) / 3.0
                    my_mean = (py1 + py2 + py3) / 3.0

                    valid.append(
                        {
                            "track": track,
                            "mx_mean": mx_mean,
                            "my_mean": my_mean,
                            "mxp1": mxp1,
                            "mxp2": mxp2,
                            "myp1": myp1,
                            "myp2": myp2,
                            "avx": avx,
                            "avy": avy,
                            "av": av,
                        }
                    )

            # Globale Analyse
            analyze(valid, g_global, "Global")

            # Viertel-Analyse
            groups = {}
            cell_w = width / 2
            cell_h = height / 2
            for info in valid:
                col = int(info["mx_mean"] // cell_w)
                row = int(info["my_mean"] // cell_h)
                groups.setdefault((col, row), []).append(info)
            for key, subset in groups.items():
                analyze(subset, g_quarter, f"Quarter {key}")

            # Achtel-Analyse
            groups = {}
            cell_w = width / 4
            cell_h = height / 2
            for info in valid:
                col = int(info["mx_mean"] // cell_w)
                row = int(info["my_mean"] // cell_h)
                groups.setdefault((col, row), []).append(info)
            for key, subset in groups.items():
                analyze(subset, g_eighth, f"Eighth {key}")

        self.report({'INFO'}, f"{len(selected_tracks)} Tracks ausgewählt")
        return {'FINISHED'}


class CLIP_OT_cleanup(bpy.types.Operator):
    bl_idname = "clip.cleanup"
    bl_label = "Cleanup"
    bl_description = (
        "Ruft 'Select Short Tracks', 'Select Error Tracks' und danach 'Delete' auf"
    )

    def execute(self, context):
        print("[Cleanup] select_short_tracks")
        if bpy.ops.clip.select_short_tracks.poll():
            bpy.ops.clip.select_short_tracks()
        else:
            print("[Cleanup] select_short_tracks nicht verf\u00fcgbar")

        print("[Cleanup] track_cleanup")
        if bpy.ops.clip.track_cleanup.poll():
            bpy.ops.clip.track_cleanup()
        else:
            print("[Cleanup] track_cleanup nicht verf\u00fcgbar")

        print("[Cleanup] delete_selected")
        if bpy.ops.clip.delete_selected.poll():
            bpy.ops.clip.delete_selected()
        else:
            print("[Cleanup] delete_selected nicht verf\u00fcgbar")

        print("[Cleanup] fertig")
        return {'FINISHED'}


class CLIP_OT_step_track(bpy.types.Operator):
    bl_idname = "clip.step_track"
    bl_label = "Step Track"
    bl_description = (
        "Führt Detect, Name Track, Select TRACK und Track Partial aus "
        "und springt anschließend um 'Frames/Track' vor"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        scene = context.scene
        step = scene.frames_track
        end_frame = scene.frame_end

        while scene.frame_current <= end_frame:
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()
            if bpy.ops.clip.prefix_track.poll():
                bpy.ops.clip.prefix_track()
            if bpy.ops.clip.select_active_tracks.poll():
                bpy.ops.clip.select_active_tracks()
            if bpy.ops.clip.track_partial.poll():
                bpy.ops.clip.track_partial()

            # Nach dem Tracken erneut Marker erkennen
            if bpy.ops.clip.all_detect.poll():
                bpy.ops.clip.all_detect()

            next_frame = scene.frame_current + step
            if next_frame > end_frame:
                break
            scene.frame_current = next_frame

        return {'FINISHED'}


class CLIP_OT_frame_jump(bpy.types.Operator):
    bl_idname = "clip.frame_jump_custom"
    bl_label = "Frame jump"
    bl_description = "Springt um 'Frames/Track' nach vorne"

    def execute(self, context):
        scene = context.scene
        step = scene.frames_track
        if step <= 0:
            self.report({'WARNING'}, "Frames/Track muss > 0 sein")
            return {'CANCELLED'}
        scene.frame_current = min(scene.frame_current + step, scene.frame_end)
        return {'FINISHED'}


class CLIP_OT_api_defaults(bpy.types.Operator):
    bl_idname = "clip.api_defaults"
    bl_label = "Defaults"
    bl_description = (
        "Setzt Standardwerte f\u00fcr Pattern, Suche, Motion Model und mehr"
    )

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = 50
        settings.default_search_size = 100
        settings.default_motion_model = 'Loc'
        settings.default_pattern_match = 'KEYFRAME'
        settings.use_default_brute = True
        settings.use_default_normalization = True
        settings.use_default_red_channel = True
        settings.use_default_green_channel = True
        settings.use_default_blue_channel = True
        settings.default_weight = 1.0
        settings.default_correlation_min = 0.9
        settings.default_margin = 100

        self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


class CLIP_OT_setup_defaults(bpy.types.Operator):
    bl_idname = "clip.setup_defaults"
    bl_label = "Test Defaults"
    bl_description = (
        "Setzt Tracking-Standards: Pattern 10, Motion Loc, Keyframe-Match"
    )

    silent: BoolProperty(default=False, options={'HIDDEN'})

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



        if not self.silent:
            self.report({'INFO'}, "Tracking-Defaults gesetzt")
        return {'FINISHED'}


class CLIP_OT_test_button(bpy.types.Operator):
    bl_idname = "clip.test_button"
    bl_label = "Test"
    bl_description = (
        "Trackt die Sequenz vorw\u00e4rts und speichert Start- und Endframe sowie Einstellungen"
    )

    def execute(self, context):
        global TEST_START_FRAME, TEST_END_FRAME, TEST_SETTINGS

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        scene = context.scene
        TEST_START_FRAME = scene.frame_current

        if bpy.ops.clip.track_markers.poll():
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        else:
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")

        TEST_END_FRAME = scene.frame_current

        settings = clip.tracking.settings
        TEST_SETTINGS = {
            "pattern_size": settings.default_pattern_size,
            "motion_model": settings.default_motion_model,
            "pattern_match": settings.default_pattern_match,
            "channels_active": (
                settings.use_default_red_channel,
                settings.use_default_green_channel,
                settings.use_default_blue_channel,
            ),
        }

        scene.frame_current = TEST_START_FRAME



        self.report({'INFO'}, "Test abgeschlossen")
        return {'FINISHED'}




class CLIP_OT_track_full(bpy.types.Operator):
    bl_idname = "clip.track_full"
    bl_label = "Track"
    bl_description = (
        "Trackt die Sequenz vorw\u00e4rts und speichert den letzten Frame"
    )

    silent: BoolProperty(default=False, options={'HIDDEN'})

    def execute(self, context):
        global TEST_START_FRAME, TEST_END_FRAME, TEST_SETTINGS, TRACKED_FRAMES, LAST_TRACK_END

        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        # Proxy aktivieren für das Tracking
        clip.use_proxy = True

        scene = context.scene
        start = scene.frame_current
        TEST_START_FRAME = start

        if bpy.ops.clip.track_markers.poll():
            bpy.ops.clip.track_markers(backwards=False, sequence=True)
        else:
            self.report({'WARNING'}, "Tracking nicht m\u00f6glich")
            return {'CANCELLED'}

        end_frame = scene.frame_current
        LAST_TRACK_END = end_frame
        TRACKED_FRAMES = end_frame - start
        if TEST_END_FRAME is None or end_frame > TEST_END_FRAME:
            TEST_END_FRAME = end_frame
            settings = clip.tracking.settings
            TEST_SETTINGS = {
                "pattern_size": settings.default_pattern_size,
                "motion_model": settings.default_motion_model,
                "pattern_match": settings.default_pattern_match,
                "channels_active": (
                    settings.use_default_red_channel,
                    settings.use_default_green_channel,
                    settings.use_default_blue_channel,
                ),
            }

        scene.frame_current = start
        if not self.silent:
            self.report({'INFO'}, f"Tracking bis Frame {end_frame} abgeschlossen")
        return {'FINISHED'}


class CLIP_OT_pattern_up(bpy.types.Operator):
    bl_idname = "clip.pattern_up"
    bl_label = "Pattern+"
    bl_description = "Erh\u00f6ht die Pattern Size um 10 %"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = max(1, int(settings.default_pattern_size * 1.1))
        settings.default_search_size = settings.default_pattern_size * 2
        return {'FINISHED'}


class CLIP_OT_pattern_down(bpy.types.Operator):
    bl_idname = "clip.pattern_down"
    bl_label = "Pattern-"
    bl_description = "Verringert die Pattern Size um 10 %"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        settings.default_pattern_size = max(1, int(settings.default_pattern_size * 0.9))
        settings.default_search_size = settings.default_pattern_size * 2
        return {'FINISHED'}


class CLIP_OT_motion_cycle(bpy.types.Operator):
    bl_idname = "clip.motion_cycle"
    bl_label = "Motion"
    bl_description = "Wechselt zum n\u00e4chsten Motion Model"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        cycle_motion_model(settings, clip, reset_size=False)
        return {'FINISHED'}


class CLIP_OT_match_cycle(bpy.types.Operator):
    bl_idname = "clip.match_cycle"
    bl_label = "Match"
    bl_description = "Schaltet das Pattern Match um"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        settings = clip.tracking.settings
        current = settings.default_pattern_match
        if current == 'KEYFRAME':
            settings.default_pattern_match = 'PREV_FRAME'
        else:
            settings.default_pattern_match = 'KEYFRAME'
        return {'FINISHED'}


class CLIP_OT_channel_r_on(bpy.types.Operator):
    bl_idname = "clip.channel_r_on"
    bl_label = "R On"
    bl_description = "Aktiviert den Rotkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_red_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_r_off(bpy.types.Operator):
    bl_idname = "clip.channel_r_off"
    bl_label = "R Off"
    bl_description = "Deaktiviert den Rotkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_red_channel = False
        return {'FINISHED'}


class CLIP_OT_channel_g_on(bpy.types.Operator):
    bl_idname = "clip.channel_g_on"
    bl_label = "G On"
    bl_description = "Aktiviert den Gr\u00fcnkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_green_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_g_off(bpy.types.Operator):
    bl_idname = "clip.channel_g_off"
    bl_label = "G Off"
    bl_description = "Deaktiviert den Gr\u00fcnkanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_green_channel = False
        return {'FINISHED'}


class CLIP_OT_channel_b_on(bpy.types.Operator):
    bl_idname = "clip.channel_b_on"
    bl_label = "B On"
    bl_description = "Aktiviert den Blaukanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_blue_channel = True
        return {'FINISHED'}


class CLIP_OT_channel_b_off(bpy.types.Operator):
    bl_idname = "clip.channel_b_off"
    bl_label = "B Off"
    bl_description = "Deaktiviert den Blaukanal"

    def execute(self, context):
        clip = context.space_data.clip
        if not clip:
            self.report({'WARNING'}, "Kein Clip geladen")
            return {'CANCELLED'}

        clip.tracking.settings.use_default_blue_channel = False
        return {'FINISHED'}



operator_classes = (
    OBJECT_OT_simple_operator,
    CLIP_OT_panel_button,
    CLIP_OT_proxy_on,
    CLIP_OT_proxy_off,
    CLIP_OT_track_nr1,
    CLIP_OT_detect_button,
    CLIP_OT_prefix_new,
    CLIP_OT_prefix_test,
    CLIP_OT_prefix_track,
    CLIP_OT_prefix_good,
    CLIP_OT_distance_button,
    CLIP_OT_delete_selected,
    CLIP_OT_select_short_tracks,
    CLIP_OT_count_button,
    CLIP_OT_api_defaults,
    CLIP_OT_defaults_detect,
    CLIP_OT_motion_detect,
    CLIP_OT_channel_detect,
    CLIP_OT_apply_settings,
    CLIP_OT_track_bidirectional,
    CLIP_OT_track_partial,
    CLIP_OT_step_track,
    CLIP_OT_frame_jump,
    CLIP_OT_setup_defaults,
    CLIP_OT_track_full,
    CLIP_OT_pattern_up,
    CLIP_OT_pattern_down,
    CLIP_OT_motion_cycle,
    CLIP_OT_match_cycle,
    CLIP_OT_channel_r_on,
    CLIP_OT_channel_r_off,
    CLIP_OT_channel_g_on,
    CLIP_OT_channel_g_off,
    CLIP_OT_channel_b_on,
    CLIP_OT_channel_b_off,
    CLIP_OT_test_button,
    CLIP_OT_all_detect,
    CLIP_OT_cycle_detect,
    CLIP_OT_all_cycle,
    CLIP_OT_track_sequence,
    CLIP_OT_tracking_length,
    CLIP_OT_playhead_to_frame,
    CLIP_OT_low_marker_frame,
    CLIP_OT_select_active_tracks,
    CLIP_OT_marker_position,
    CLIP_OT_good_marker_position,
    CLIP_OT_camera_solve,
    CLIP_OT_track_cleanup,
    CLIP_OT_cleanup,
)

