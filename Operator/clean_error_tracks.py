# Operator/clean_error_tracks.py

import bpy

# 👉 Dichte-Pruning als erster Schritt verfügbar machen
from ..Helper.prune_tracks_density import prune_tracks_density

def track_has_internal_gaps(track):
    frames = sorted([m.frame for m in track.markers])
    if len(frames) < 3:
        return False
    return any(frames[i] - frames[i - 1] > 1 for i in range(1, len(frames)))

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

        # Gültigen CLIP_EDITOR-Kontext finden
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

        # --- 1) Dichte-Pruning als erster Schritt ---
        prune_res = prune_tracks_density(context, threshold_key="marker_frame", dry_run=False)
        if prune_res.get("status") != "ok":
            print(f"[PruneDensity] status={prune_res.get('status')}")
        else:
            print(f"[PruneDensity] frames_processed={prune_res.get('frames_processed')} "
                  f"deleted_tracks={prune_res.get('deleted_tracks')} "
                  f"threshold={prune_res.get('threshold')}")
        # Depsgraph/Layer synchronisieren und Clip/Tracks neu binden
        with context.temp_override(area=clip_editor_area, region=clip_editor_region, space_data=clip_editor_space):
            deps = context.evaluated_depsgraph_get()
            deps.update()
            bpy.context.view_layer.update()
            scene.frame_set(scene.frame_current)

        # --- 2) Grid-basierter Error-Clean (bestehende Pipeline) ---
# --- 2) Multiscale Grid-Error-Clean (inkl. Drift & Micro-Pass) ---
        clip = clip_editor_space.clip
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)
        deleted = multiscale_temporal_grid_clean(
            context, clip_editor_area, clip_editor_region, clip_editor_space,
            list(clip.tracking.tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=3,
            outlier_q=0.90, hysteresis_hits=2, min_cell_items=4
        )
        print(f"[MultiScale] total deleted: {deleted}")

        clip = clip_editor_space.clip
        tracks = clip.tracking.tracks

        # --- 3) Gap-Erkennung & Aufteilung ---
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
