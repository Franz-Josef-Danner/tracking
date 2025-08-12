import bpy
import time

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


def run_cleanup_in_region(context, area, region, space, tracks, frame_range,
                          xmin, xmax, ymin, ymax, ee, width, height,
                          redraw_every=25):
    total_deleted = 0
    frame_start, frame_end = frame_range
    deletes_since_redraw = 0

    # Ganzes Cleaning im gültigen UI-Kontext ausführen – optimiert
    with context.temp_override(area=area, region=region, space_data=space):
        wm = context.window_manager
        wm.progress_begin(0, max(1, (frame_end - frame_start)))
        redraw_every_frames = 20  # UI-Update nur gelegentlich
        to_delete = []            # (track, frame)-Paare sammeln
    
        for fi in range(frame_start + 1, frame_end - 1):
            f1, f2 = fi - 1, fi + 1
            marker_data = []
    
            # Datenaufnahme (Positions- und Geschwindigkeitsableitung)
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
                # leichtes Fortschritts- und Header-Update gedrosselt
                if (fi - frame_start) % redraw_every_frames == 0:
                    wm.progress_update(fi - frame_start)
                    area.header_text_set(f"Cleanup {fi}/{frame_end-1} | deleted {total_deleted}")
                    region.tag_redraw()
                continue
    
            # Durchschnitt und Abweichungen
            vxa = sum(vx for _, vx, _ in marker_data) / len(marker_data)
            vya = sum(vy for _, _, vy in marker_data) / len(marker_data)
            va = (vxa + vya) / 2
    
            # Direktes Schwellenkriterium – kein iteratives eb-Shrinking
            for track, vx, vy in marker_data:
                vm = (vx + vy) / 2
                if abs(vm - va) >= ee:
                    to_delete.append((track, f1))
                    to_delete.append((track, fi))
                    to_delete.append((track, f2))
    
            # Batch-Delete am Ende jedes fi
            if to_delete:
                # Duplikate vermeiden (selber Track/Frame mehrfach gesammelt)
                seen = set()
                for trk, frm in to_delete:
                    key = (id(trk), frm)
                    if key in seen:
                        continue
                    seen.add(key)
                    if trk.markers.find_frame(frm):
                        trk.markers.delete_frame(frm)
                        total_deleted += 1
                to_delete.clear()
    
            # Gedrosselte, leichte UI-Signale
            if (fi - frame_start) % redraw_every_frames == 0:
                wm.progress_update(fi - frame_start)
                area.header_text_set(f"Cleanup {fi}/{frame_end-1} | deleted {total_deleted}")
                region.tag_redraw()
    
        # Blockende: Fortschritt/Header zurücksetzen, letzter Redraw-Hint
        wm.progress_end()
        area.header_text_set(None)
        region.tag_redraw()


    return total_deleted

def clean_error_tracks(context, space, area=None, region=None):
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
                    context, area, region, space,
                    tracks, frame_range, xmin, xmax, ymin, ymax, ee, width, height,
                    redraw_every=2
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
    except Exception as e:
        return False

# 🆕 Zusatz: robuster Name-Zugriff (UTF-8 tolerant)
def _safe_name(obj):
    """Gibt einen robusten Track-Namen zurück oder None bei Problemen."""
    try:
        n = getattr(obj, "name", None)
        if n is None:
            return None
        if isinstance(n, bytes):
            n = n.decode("utf-8", errors="ignore")
        else:
            n = str(n)
        n = n.strip()
        return n or None
    except Exception:
        return None

def mute_marker_path(track, from_frame, direction, mute=True):
    try:
        markers = list(track.markers)  # Snapshot – verhindert Collection-Invalidation
    except Exception:
        return
    fcmp = (lambda f: f >= from_frame) if direction == 'forward' else (lambda f: f <= from_frame)
    for m in markers:
        try:
            if m and fcmp(m.frame):
                # Guard: Marker kann durch vorherige Ops invalid sein
                _ = m.co  # touch to validate RNA
                m.mute = bool(mute)
        except ReferenceError:
            # Marker wurde zwischenzeitlich gelöscht/ersetzt – einfach überspringen
            continue
        except Exception:
            # Keine Eskalation an dieser Stelle: Stabilität > Strenge
            continue

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
    # Segment-Frames als Set erfassen
    segments = get_track_segments(track)
    valid_frames = set()
    for segment in segments:
        valid_frames.update(segment)

    # Alle Marker prüfen
    for marker in track.markers:
        if marker.frame not in valid_frames:
            marker.mute = True

def mute_all_outside_segment_markers(tracks):
    for track in tracks:
        mute_outside_segment_markers(track)

def clear_path_on_split_tracks_segmented(context, area, region, space, original_tracks, new_tracks):
    clip = space.clip

    # 1) Rebinding: frische RNA-Objekte holen (verhindert stale Refs nach Copy/Paste)
    # (robust gegen nicht-UTF-8-Namen)
    tracks_by_name = {}
    for t in clip.tracking.tracks:
        tn = _safe_name(t)
        if tn:
            tracks_by_name[tn] = t

    ot = []
    for n in original_tracks:
        nn = _safe_name(n)
        if nn and nn in tracks_by_name:
            ot.append(tracks_by_name[nn])
    original_tracks = ot

    nt = []
    for n in new_tracks:
        nn = _safe_name(n)
        if nn and nn in tracks_by_name:
            nt.append(tracks_by_name[nn])
    new_tracks = nt

    redraw_budget = 0

    with context.temp_override(area=area, region=region, space_data=space):
        # 🔴 ORIGINAL-TRACKS: vorderes Segment behalten → danach muten
        for track in original_tracks:
            # Snapshot der Segmente, um Collection-Änderungen während des Loops zu entkoppeln
            segments = list(get_track_segments(track))
            for seg in segments:
                mute_marker_path(track, seg[-1] + 1, 'forward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()

        # 🔵 NEW-TRACKS: hinteres Segment behalten → davor muten
        for track in new_tracks:
            segments = list(get_track_segments(track))
            for seg in segments:
                mute_marker_path(track, seg[0] - 1, 'backward', mute=True)
                redraw_budget += 1
                if redraw_budget % 25 == 0:
                    region.tag_redraw()

        # 2) Einmalige harte Synchronisation am Blockende
        deps = context.evaluated_depsgraph_get()
        deps.update()
        bpy.context.view_layer.update()
        region.tag_redraw()

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def execute(self, context):
        scene = context.scene
        clip_editor_area = clip_editor_region = clip_editor_space = None

        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        clip_editor_area = area
                        clip_editor_region = region
                        clip_editor_space = area.spaces.active

        if not clip_editor_space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        clean_error_tracks(context, clip_editor_space, clip_editor_area, clip_editor_region)
        clip = clip_editor_space.clip
        tracks = clip.tracking.tracks

        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]
        if not original_tracks:
            self.report({'INFO'}, "Keine Tracks mit Lücken gefunden.")
            return {'FINISHED'}

        existing_names = {t.name for t in tracks}
        for t in tracks:
            t.select = False
        for t in original_tracks:
            t.select = True

        # RICHTIG: verwende die zuvor ermittelten Clip-Editor-Handles
        with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=clip_editor_space):
            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        clear_path_on_split_tracks_segmented(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            original_tracks, new_tracks
        )

        # 🧩 Jetzt rekursiv weiter, bis keine Gaps mehr bestehen
        recursive_split_cleanup(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            tracks
        )

        clear_path_on_split_tracks_segmented(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            original_tracks, new_tracks
        )


        # 🔒 Safety Pass: Einzelne Marker muten
        mute_unassigned_markers(tracks)

        # ✅ Ganz am Ende: Track-Ende muten (nach Abschluss aller Rekursionen)
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)

        return {'FINISHED'}

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

        # Track-Anfangsframe bestimmen (kleinster Marker-Frame im Track)
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

        # Hole verarbeitete Track-Namen als reguläre Python-Liste
        processed = list(scene.get("processed_tracks", []))

        # Finde nur Tracks mit Gaps, die noch nicht verarbeitet wurden
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
            deps = context.evaluated_depsgraph_get()
            deps.update()                       # robuste Depsgraph-Synchronisation
            bpy.context.view_layer.update()     # Layer-Update
            scene.frame_set(scene.frame_current)


        all_names_after = {t.name for t in tracks}
        new_names = all_names_after - existing_names
        new_tracks = [t for t in tracks if t.name in new_names]

        # Tracks (original und neu) als verarbeitet markieren
        for t in original_tracks + new_tracks:
            if t.name not in processed:
                processed.append(t.name)

        # Rückspeichern
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
