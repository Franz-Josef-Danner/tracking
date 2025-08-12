import bpy
from ..Helper.multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from ..Helper.prune_tracks_density import prune_tracks_density

from ..Helper.segments import track_has_internal_gaps, get_track_segments
from ..Helper.naming import _safe_name
from ..Helper.mute_ops import mute_marker_path, mute_after_last_marker, mute_unassigned_markers
from ..Helper.split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup

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
