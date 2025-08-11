import bpy
import time

hasattr(bpy.ops.clip, "clean_error_tracks_modal"), hasattr(bpy.ops.clip, "clean_error_tracks")

def get_marker_position(track, frame):
    marker = track.markers.find_frame(frame)
    if marker:
        return marker.co
    return None


def track_has_internal_gaps(track):
    frames = sorted([m.frame for m in track.markers])
    if len(frames) < 3:
        return False
    return any(frames[i] - frames[i - 1] > 1 for i in range(1, len(frames)))


def run_cleanup_in_region(tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height):
    total_deleted = 0
    frame_start, frame_end = frame_range

    for fi in range(frame_start + 1, frame_end - 1):
        f1, f2 = fi - 1, fi + 1
        marker_data = []

        for track in tracks:
            p1 = get_marker_position(track, f1)
            p2 = get_marker_position(track, fi)
            p3 = get_marker_position(track, f2)

            if not (p1 and p2 and p3):
                continue

            x, y = p2[0] * width, p2[1] * height
            if not (xmin <= x < xmax and ymin <= y < ymax):
                continue

            vxm = (p2[0] - p1[0]) + (p3[0] - p2[0])
            vym = (p2[1] - p1[1]) + (p3[1] - p2[1])
            marker_data.append((track, vxm, vym))

        if not marker_data:
            continue

        vxa = sum(vx for _, vx, _ in marker_data) / len(marker_data)
        vya = sum(vy for _, _, vy in marker_data) / len(marker_data)
        va = (vxa + vya) / 2

        eb = max([abs((vx + vy) / 2 - va) for _, vx, vy in marker_data], default=0.0001)
        eb = max(eb, 0.0001)

        while eb > ee:
            eb *= 0.95
            for track, vx, vy in marker_data:
                vm = (vx + vy) / 2
                if abs(vm - va) >= eb:
                    for f in (f1, fi, f2):
                        if track.markers.find_frame(f):
                            track.markers.delete_frame(f)
                            total_deleted += 1
                            # Entfernt: time.sleep(0.02)

    return total_deleted


def clean_error_tracks(context, space):
    scene = context.scene
    clip = space.clip
    tracks = clip.tracking.tracks

    for track in tracks:
        track.select = False

    width, height = clip.size
    frame_range = (scene.frame_start, scene.frame_end)

    ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
    fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
    teilfaktoren = [1, 2, 4]

    total_deleted_all = 0
    for ee, division in zip(fehlergrenzen, teilfaktoren):
        for xIndex in range(division):
            for yIndex in range(division):
                xmin = xIndex * (width / division)
                xmax = (xIndex + 1) * (width / division)
                ymin = yIndex * (height / division)
                ymax = (yIndex + 1) * (height / division)
                total_deleted_all += run_cleanup_in_region(
                    tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height
                )
    return total_deleted_all, 0.0


def delete_marker_path(track, from_frame, direction):
    to_delete = []
    for m in track.markers:
        if (direction == 'forward' and m.frame >= from_frame) or \
           (direction == 'backward' and m.frame <= from_frame):
            to_delete.append(m.frame)

    for f in to_delete:
        track.markers.delete_frame(f)


def get_track_segments(track):
    frames = sorted([m.frame for m in track.markers])
    if not frames:
        return []

    segments = []
    current_segment = [frames[0]]
    for i in range(1, len(frames)):
        if frames[i] - frames[i - 1] == 1:
            current_segment.append(frames[i])
        else:
            segments.append(current_segment)
            current_segment = [frames[i]]
    segments.append(current_segment)
    return segments


# 🆕 Neue Hilfsfunktion hier einfügen:
def is_marker_valid(track, frame):
    try:
        marker = track.markers.find_frame(frame)
        return marker is not None and hasattr(marker, "co")
    except Exception:
        return False


def mute_marker_path(track, from_frame, direction, mute=True):
    for m in track.markers:
        if (direction == 'forward' and m.frame >= from_frame) or \
           (direction == 'backward' and m.frame <= from_frame):
            m.mute = mute


def mute_after_last_marker(track, scene_end):
    """
    Mutet alle Marker nach dem letzten gültigen Segment-Ende.
    """
    segments = get_track_segments(track)
    if not segments:
        return

    last_valid_frame = segments[-1][-1]  # Letzter Frame des letzten gültigen Segments

    for m in track.markers:
        if m.frame >= last_valid_frame and m.frame <= scene_end:
            m.mute = True


def mute_outside_segment_markers(track):
    """
    Mutes all markers in the given track that are not part of a continuous segment.
    """
    segments = get_track_segments(track)
    valid_frames = set()
    for segment in segments:
        valid_frames.update(segment)

    for marker in track.markers:
        if marker.frame not in valid_frames:
            marker.mute = True


def mute_all_outside_segment_markers(tracks):
    for track in tracks:
        mute_outside_segment_markers(track)


def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    with context.temp_override(area=area, region=region, space_data=space):

        # 🔴 ORIGINAL-TRACKS: Vorderes Segment behalten → alles danach muten
        for track in original_tracks:
            segments = get_track_segments(track)

            # Optional: alle Marker vorher ent-muten (wie ENABLE)
            for m in track.markers:
                m.mute = False

            for seg in segments:
                mute_marker_path(track, seg[-1] + 1, 'forward', mute=True)
        # Entfernt: time.sleep()

        # 🔵 NEW-TRACKS: Hinteres Segment behalten → alles davor muten
        for track in new_tracks:
            # UI-Update forcieren
            context.scene.frame_set(context.scene.frame_current)
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            bpy.context.view_layer.update()

            segments = get_track_segments(track)

            # Optional: alle Marker vorher ent-muten (wie ENABLE)
            for m in track.markers:
                m.mute = False

            for seg in segments:
                mute_marker_path(track, seg[0] - 1, 'backward', mute=True)
        # Entfernt: time.sleep()

# =========================
# 🆕 Modal-Operator (UI-responsiv)
# =========================

class CLIP_OT_clean_error_tracks_modal(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks_modal"
    bl_label = "Clean Error Tracks (Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return bpy.ops.clip.clean_error_tracks_modal('INVOKE_DEFAULT')

    _timer = None
    _state = None  # dict mit Phasen- und Fortschrittszustand

    def _find_clip_context(self, context):
        area = region = space = None
        for a in context.screen.areas:
            if a.type == 'CLIP_EDITOR':
                for r in a.regions:
                    if r.type == 'WINDOW':
                        area, region, space = a, r, a.spaces.active
                        break
        return area, region, space

    def _set_header(self, context, text):
        try:
            if context.area:
                context.area.header_text_set(text)
        except Exception:
            pass
        try:
            if self._state and self._state.get("area"):
                self._state["area"].header_text_set(text)
        except Exception:
            pass

    def invoke(self, context, event):
        area, region, space = self._find_clip_context(context)
        if not space or not space.clip:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext.")
            return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)

        scene = context.scene
        clip = space.clip
        width, height = clip.size
        frame_range = (scene.frame_start, scene.frame_end)

        ee_base = (getattr(scene, "error_track", 1.0) + 0.1) / 100
        fehlergrenzen = [ee_base, ee_base / 2, ee_base / 4]
        teilfaktoren = [1, 2, 4]

        total_cells = sum(d * d for d in teilfaktoren)
        wm.progress_begin(0, total_cells)

        self._state = {
            "area": area, "region": region, "space": space,
            "scene": scene, "clip": clip,
            "width": width, "height": height, "frame_range": frame_range,
            "fehlergrenzen": fehlergrenzen, "teilfaktoren": teilfaktoren,

            "phase": 1,
            "p1_idx": 0,          # Index über fehlergrenzen/teilfaktoren
            "p1_x": 0, "p1_y": 0, # Zellkoordinaten
            "p1_done": 0,         # Fortschritt für Progressbar

            "p2_done": False,     # Duplikation+Split durchgeführt
            "p3_started": False,  # Rekursiv gestartet
        }

        self._set_header(context, "Phase 1/3: Grid-Cleanup läuft …")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        s = self._state
        area, region, space = s["area"], s["region"], s["space"]

        if s["phase"] == 1:
            idx = s["p1_idx"]
            if idx >= len(s["fehlergrenzen"]):
                s["phase"] = 2
                self._set_header(context, "Phase 2/3: Duplikation & Segment-Split …")
                return {'RUNNING_MODAL'}

            ee = s["fehlergrenzen"][idx]
            div = s["teilfaktoren"][idx]

            xIndex, yIndex = s["p1_x"], s["p1_y"]
            width, height = s["width"], s["height"]

            xmin = xIndex * (width / div)
            xmax = (xIndex + 1) * (width / div)
            ymin = yIndex * (height / div)
            ymax = (yIndex + 1) * (height / div)

            tracks = space.clip.tracking.tracks
            run_cleanup_in_region(
                tracks, s["frame_range"], xmin, xmax, ymin, ymax, ee, width, height
            )

            s["p1_done"] += 1
            context.window_manager.progress_update(s["p1_done"])
            area.tag_redraw()

            # Zellzeiger erhöhen
            if s["p1_x"] + 1 < div:
                s["p1_x"] += 1
            else:
                s["p1_x"] = 0
                if s["p1_y"] + 1 < div:
                    s["p1_y"] += 1
                else:
                    s["p1_y"] = 0
                    s["p1_idx"] += 1

            return {'RUNNING_MODAL'}

        if s["phase"] == 2:
            if not s["p2_done"]:
                self._phase2_duplicate_and_split(context, s)
                s["p2_done"] = True
                area.tag_redraw()
            s["phase"] = 3
            self._set_header(context, "Phase 3/3: Rekursiver Split-Cleanup …")
            return {'RUNNING_MODAL'}

        if s["phase"] == 3:
            if not s["p3_started"]:
                self._phase3_recursive_cleanup(context, s)
                s["p3_started"] = True
                return self._finish(context)
            return self._finish(context)

        return {'RUNNING_MODAL'}

    def _phase2_duplicate_and_split(self, context, s):
        area, region, space = s["area"], s["region"], s["space"]
        clip = space.clip
        tracks = clip.tracking.tracks

        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            return

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=3)
            context.scene.frame_set(context.scene.frame_current)
            bpy.context.view_layer.update()

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        clear_path_on_split_tracks_segmented(
            context, area, region, space, original_tracks, new_tracks
        )

    def _phase3_recursive_cleanup(self, context, s):
        area, region, space = s["area"], s["region"], s["space"]
        tracks = space.clip.tracking.tracks

        recursive_split_cleanup(context, area, region, space, tracks)

        # Safety-Pässe nach der Rekursion
        mute_unassigned_markers(tracks)
        for t in tracks:
            mute_after_last_marker(t, context.scene.frame_end)

    def _finish(self, context):
        wm = context.window_manager
        wm.progress_end()
        self._set_header(context, None)
        if self._timer:
            wm.event_timer_remove(self._timer)
        return {'FINISHED'}


class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        # Übergabe an den nicht-blockierenden Modal-Operator
        return bpy.ops.clip.clean_error_tracks_modal('INVOKE_DEFAULT')


def mute_unassigned_markers(tracks):
    """
    Mute alle Marker, die:
    - nicht Teil eines ≥2-Frames langen Segments sind
    - oder exakt am Track-Anfang liegen (auch wenn im Segment enthalten)
    """
    for track in tracks:
        segments = get_track_segments(track)
        valid_frames = set()
        for segment in segments:
            if len(segment) >= 2:
                valid_frames.update(segment)

        if not track.markers:
            continue
        first_frame = min(m.frame for m in track.markers)

        for marker in track.markers:
            f = marker.frame
            if f not in valid_frames or f == first_frame:
                marker.mute = True


def recursive_split_cleanup(context, area, region, space, tracks):
    scene = context.scene
    iteration = 0
    previous_gap_count = -1
    MAX_ITERATIONS = 5

    # Initialisieren (falls nicht vorhanden)
    if "processed_tracks" not in scene:
        scene["processed_tracks"] = []

    while iteration < MAX_ITERATIONS:
        iteration += 1

        processed = list(scene.get("processed_tracks", []))

        original_tracks = [
            t for t in tracks
            if track_has_internal_gaps(t) and t.name not in processed
        ]

        if not original_tracks:
            break

        if previous_gap_count == len(original_tracks):
            break

        previous_gap_count = len(original_tracks)

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        with context.temp_override(area=area, region=region, space_data=space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=5)
            scene.frame_set(scene.frame_current)
            bpy.context.view_layer.update()
            # Entfernt: time.sleep(0.2)

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        for t in original_tracks + new_tracks:
            if t.name not in processed:
                processed.append(t.name)

        scene["processed_tracks"] = processed

        clear_path_on_split_tracks_segmented(
            context, area, region, space,
            original_tracks, new_tracks
        )

    # 🔚 Letzter Schritt: kurze Tracks bereinigen – im gültigen UI-Kontext
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.clean_short_tracks('INVOKE_DEFAULT')

    # 🧩 Danach: Vereinzelte Marker, die außerhalb von Segmenten liegen, muten
    mute_unassigned_markers(tracks)

    return {'FINISHED'}
