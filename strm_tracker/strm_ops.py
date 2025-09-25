import bpy
from .strm_utils import (
    extract_grayscale_frames,
    analyze_strm,
    compute_tile_coords,
    select_top_tiles_as_rois,
    extract_single_grayscale_frame,
    detect_features_in_roi,
    extract_grayscale_frames_range,
    track_markers_lk,
    compute_track_kpis,
    filter_tracks_and_kpis,
    correspondences_from_tracks,
    fit_motion_models_all,
    promotion_step,
)
from .strm_overlay import draw_tile_overlay_callback, get_overlay_state


class STRM_OT_Analyze(bpy.types.Operator):
    bl_idname = "clip.strm_analyze"
    bl_label = "STRM Analyse"
    bl_description = "Analysiert das Video in Tiles und berechnet Texture/Motion Scores"

    def execute(self, context):
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        try:
            frames = extract_grayscale_frames(clip, start=0, count=10)
        except Exception as e:
            self.report({'ERROR'}, f"Fehler beim Lesen der Frames: {e}")
            return {'CANCELLED'}

        if not frames:
            self.report({'ERROR'}, "Fehler beim Lesen der Frames.")
            return {'CANCELLED'}

        try:
            tile_data = analyze_strm(frames, tile_rows=4, tile_cols=6)
        except Exception as e:
            self.report({'ERROR'}, f"Fehler bei STRM-Analyse: {e}")
            return {'CANCELLED'}

        # Ergebnisse in Szene speichern (für Overlay)
        overlay = get_overlay_state(context.scene)
        overlay["tiles"] = tile_data
        overlay["enabled"] = True
        overlay["score_type"] = overlay.get("score_type", "motion")

        print("\n[STRM-Ausgabe]")
        for idx, t in enumerate(tile_data):
            print(
                f"Tile {idx} (r{t['tile'][0]}c{t['tile'][1]}): "
                f"Texture={t['texture']:.3f}, Motion={t['motion']:.3f}, "
                f"Divergence={t['div']:.3f}, Flicker={t['flicker']:.3f}"
            )

        self.report({'INFO'}, f"{len(tile_data)} Tiles analysiert.")
        return {'FINISHED'}


_draw_handle = None


class STRM_OT_ToggleOverlay(bpy.types.Operator):
    bl_idname = "clip.strm_toggle_overlay"
    bl_label = "Toggle STRM Overlay"
    bl_description = "Zeigt/versteckt das STRM Tile-Gitter"

    tile_rows = bpy.props.IntProperty(name="Rows", default=4, min=1, max=64)
    tile_cols = bpy.props.IntProperty(name="Cols", default=6, min=1, max=64)

    def execute(self, context):
        global _draw_handle

        scene = context.scene
        overlay = get_overlay_state(scene)
        enabled = not overlay.get("enabled", False)
        overlay["enabled"] = enabled

        if enabled:
            clip = context.edit_movieclip
            if not clip:
                self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
                overlay["enabled"] = False
                return {'CANCELLED'}

            overlay["tiles"] = compute_tile_coords(clip, self.tile_rows, self.tile_cols)

            if _draw_handle is None:
                _draw_handle = bpy.types.SpaceClipEditor.draw_handler_add(
                    draw_tile_overlay_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        else:
            if _draw_handle is not None:
                bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
                _draw_handle = None

        # Region neu zeichnen
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()
        return {'FINISHED'}


class STRM_OT_SetOverlayScore(bpy.types.Operator):
    bl_idname = "clip.strm_set_overlay_score"
    bl_label = "Set STRM Overlay Score"
    bl_description = "Wählt den Score-Typ für das farbige Overlay"

    items = [
        ('motion', "Motion", "Bewegung"),
        ('texture', "Texture", "Textur"),
        ('div', "Divergence", "Divergenz"),
        ('flicker', "Flicker", "Helligkeitsschwankung"),
    ]
    score_type = bpy.props.EnumProperty(name="Score", items=items, default='motion')

    def execute(self, context):
        overlay = get_overlay_state(context.scene)
        overlay["score_type"] = self.score_type

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()
        return {'FINISHED'}


class STRM_OT_SelectROIs(bpy.types.Operator):
    bl_idname = "clip.strm_select_rois"
    bl_label = "STRM: Select ROIs"
    bl_description = "Wählt Top-N STRM-Tiles als ROIs basierend auf Score"

    top_n = bpy.props.IntProperty(name="Top N", default=6, min=1, max=100)
    score_type = bpy.props.EnumProperty(
        name="Score Type",
        items=[
            ("motion", "Motion", ""),
            ("texture", "Texture", ""),
            ("div", "Divergence", ""),
            ("flicker", "Flicker", ""),
        ],
        default="motion",
    )

    def execute(self, context):
        overlay = get_overlay_state(context.scene)
        tiles = overlay.get("tiles", [])
        if not tiles:
            self.report({'ERROR'}, "Keine STRM-Tiles gefunden.")
            return {'CANCELLED'}

        rois = select_top_tiles_as_rois(
            tiles,
            score_type=self.score_type,
            top_n=self.top_n,
            min_distance_px=20,
        )

        overlay["rois"] = rois
        overlay["score_type"] = self.score_type

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{len(rois)} ROIs gewählt (nach {self.score_type})")
        return {'FINISHED'}


class STRM_OT_SeedFeatures(bpy.types.Operator):
    bl_idname = "clip.strm_seed_features"
    bl_label = "STRM: Seed Features"
    bl_description = "Seede Keypoints in den ausgewählten ROIs"

    max_features_per_roi = bpy.props.IntProperty(name="Max/ROI", default=50, min=1, max=500)
    quality_level = bpy.props.FloatProperty(name="Quality", default=0.01, min=0.0001, max=0.1)
    min_distance = bpy.props.IntProperty(name="Min Dist", default=5, min=1, max=50)

    def execute(self, context):
        scene = context.scene
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        overlay = get_overlay_state(scene)
        rois = overlay.get("rois", [])
        if not rois:
            self.report({'ERROR'}, "Keine ROIs zum Seeden.")
            return {'CANCELLED'}

        frame_num = scene.frame_current
        gray = extract_single_grayscale_frame(clip, frame_num)
        if gray is None:
            self.report({'ERROR'}, "Frame konnte nicht gelesen werden.")
            return {'CANCELLED'}

        all_points = []
        try:
            for roi in rois:
                pts = detect_features_in_roi(
                    gray,
                    roi,
                    max_features=self.max_features_per_roi,
                    quality=self.quality_level,
                    min_distance=self.min_distance,
                )
                all_points.extend(pts)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        overlay["markers"] = all_points

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{len(all_points)} Features gesät.")
        return {'FINISHED'}


class STRM_OT_TrackMarkers(bpy.types.Operator):
    bl_idname = "clip.strm_track_markers"
    bl_label = "STRM: Track Features"
    bl_description = "Trackt Marker über mehrere Frames (Lucas-Kanade)"

    num_frames = bpy.props.IntProperty(name="Frames", default=10, min=2, max=200)

    def execute(self, context):
        scene = context.scene
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        overlay = get_overlay_state(scene)
        markers = overlay.get("markers", [])
        if not markers:
            self.report({'ERROR'}, "Keine Marker zum Tracken.")
            return {'CANCELLED'}

        start_frame = scene.frame_current
        frames = extract_grayscale_frames_range(clip, start_frame, self.num_frames)
        if len(frames) < 2:
            self.report({'ERROR'}, "Nicht genügend Frames geladen.")
            return {'CANCELLED'}

        try:
            tracks = track_markers_lk(frames, markers)
        except RuntimeError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

        overlay["tracks"] = tracks

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{len(tracks)} Marker getrackt über {len(frames)} Frames.")
        return {'FINISHED'}


class STRM_OT_EvalKPIs(bpy.types.Operator):
    bl_idname = "clip.strm_eval_kpis"
    bl_label = "STRM: Evaluate KPIs"
    bl_description = "Berechnet KPIs für alle Tracks"

    patch_size = bpy.props.IntProperty(name="Patch", default=11, min=5, max=31)

    def execute(self, context):
        scene = context.scene
        clip = context.edit_movieclip
        if not clip:
            self.report({'ERROR'}, "Kein MovieClip ausgewählt.")
            return {'CANCELLED'}

        overlay = get_overlay_state(scene)
        tracks = overlay.get("tracks", [])
        if not tracks:
            self.report({'ERROR'}, "Keine Tracks zum Bewerten.")
            return {'CANCELLED'}

        start_frame = scene.frame_current
        num_frames = len(tracks[0])
        gray_frames = extract_grayscale_frames_range(clip, start_frame, num_frames)
        if len(gray_frames) < num_frames:
            # wir rechnen mit dem, was da ist
            pass

        kpi_results = []
        for track in tracks:
            kpis = compute_track_kpis(track, gray_frames, patch_size=self.patch_size)
            if kpis is None:
                kpis = {"survival": 0.0, "corr_median": 0.0, "residual_rms": 1e6}
            kpi_results.append(kpis)

        overlay["kpis"] = kpi_results

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"KPI-Auswertung für {len(kpi_results)} Tracks durchgeführt.")
        return {'FINISHED'}


class STRM_OT_CleanupTracks(bpy.types.Operator):
    bl_idname = "clip.strm_cleanup_tracks"
    bl_label = "STRM: Cleanup Tracks"
    bl_description = "Entfernt schlechte oder zu kurze Tracks anhand der KPIs"

    min_survival = bpy.props.FloatProperty(name="Min Survival", default=0.6, min=0.0, max=1.0)
    min_corr = bpy.props.FloatProperty(name="Min Corr", default=0.6, min=-1.0, max=1.0)
    max_rms = bpy.props.FloatProperty(name="Max RMS", default=2.0, min=0.0)
    min_length = bpy.props.IntProperty(name="Min Length", default=4, min=1)

    def execute(self, context):
        overlay = get_overlay_state(context.scene)
        tracks = overlay.get("tracks", [])
        kpis = overlay.get("kpis", [])
        if not tracks or not kpis:
            self.report({'ERROR'}, "Es fehlen Tracks oder KPIs.")
            return {'CANCELLED'}

        before = len(tracks)
        filtered_tracks, filtered_kpis = filter_tracks_and_kpis(
            tracks,
            kpis,
            min_survival=self.min_survival,
            min_corr=self.min_corr,
            max_rms=self.max_rms,
            min_length=self.min_length,
        )

        overlay["tracks"] = filtered_tracks
        overlay["kpis"] = filtered_kpis
        after = len(filtered_tracks)

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"{before - after} von {before} Tracks entfernt.")
        return {'FINISHED'}


class STRM_OT_FitMotionModel(bpy.types.Operator):
    bl_idname = "clip.strm_fit_motion_model"
    bl_label = "STRM: Fit Motion Model (RANSAC)"
    bl_description = "Fittet ein globales Motion-Modell über Tracks (Frame-Paar)"

    frame_offset = bpy.props.IntProperty(name="Frame Offset", default=5, min=1, max=100)
    lambda_penalty = bpy.props.FloatProperty(name="λ penalty", default=0.12, min=0.0, max=1.0)
    ransac_thresh = bpy.props.FloatProperty(name="RANSAC thr (px)", default=3.0, min=0.5, max=10.0)
    min_inliers = bpy.props.IntProperty(name="Min Inliers", default=8, min=3, max=100)

    def execute(self, context):
        import numpy as np

        overlay = get_overlay_state(context.scene)
        tracks = overlay.get("tracks", [])
        if not tracks:
            self.report({'ERROR'}, "Keine Tracks vorhanden.")
            return {'CANCELLED'}

        f0 = 0
        f1 = min(int(self.frame_offset), len(tracks[0]) - 1)
        A, B, idx_map = correspondences_from_tracks(tracks, f0, f1)
        if A is None or A.shape[0] < 3:
            self.report({'ERROR'}, "Zu wenige Korrespondenzen.")
            return {'CANCELLED'}

        best, all_fits = fit_motion_models_all(
            A, B,
            lam=float(self.lambda_penalty),
            ransac_thresh=float(self.ransac_thresh),
            min_inliers=int(self.min_inliers),
        )
        if best is None:
            self.report({'ERROR'}, "Kein Modell erfüllt die Min-Inliers.")
            return {'CANCELLED'}

        overlay["motion_model"] = {
            "type": best["type"],
            "M": best["M"].tolist(),
            "rms": float(best["rms"]),
            "score_S": float(best["score_S"]),
            "inliers_count": int(np.sum(best["inliers"])),
            "total": int(best["total"]),
            "inliers_mask": best["inliers"].astype(bool).tolist(),
            "f0": int(f0),
            "f1": int(f1),
        }

        overlay["motion_model_candidates"] = [
            ({
                "type": f.get("type"),
                "rms": float(f.get("rms")) if f and f.get("rms") is not None else None,
                "S": float(f.get("score_S")) if f and f.get("score_S") is not None else None,
                "inliers": int(np.sum(f.get("inliers"))) if f and f.get("inliers") is not None else 0,
            } if f else None)
            for f in all_fits
        ]

        # Redraw
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

        self.report({'INFO'}, f"Bestes Modell: {best['type']} | RMS={best['rms']:.3f} | S={best['score_S']:.3f} | Inliers={int(np.sum(best['inliers']))}/{best['total']}")
        return {'FINISHED'}


class STRM_OT_PromotionStep(bpy.types.Operator):
    bl_idname = "clip.strm_promotion_step"
    bl_label = "STRM: Promotion Step"
    bl_description = "Führt einen Promotions-/Rollback-Schritt für das Motion-Modell aus (rollierend)"

    frame_offset = bpy.props.IntProperty(
        name="Frame Offset", default=5, min=1, max=100
    )
    lambda_penalty = bpy.props.FloatProperty(
        name="λ penalty", default=0.12, min=0.0, max=1.0
    )
    ransac_thresh = bpy.props.FloatProperty(
        name="RANSAC thr (px)", default=3.0, min=0.5, max=10.0
    )

    def execute(self, context):
        import numpy as np

        scene = context.scene
        overlay = scene.get("strm_overlay", {})
        tracks = overlay.get("tracks", [])
        if not tracks:
            self.report({'ERROR'}, "Keine Tracks vorhanden.")
            return {'CANCELLED'}

        # Korrespondenzen aus aktuellem Trackingfenster
        f0 = 0
        f1 = min(self.frame_offset, len(tracks[0]) - 1)
        A, B, _ = correspondences_from_tracks(tracks, f0, f1)
        if A is None or A.shape[0] < 8:
            self.report({'ERROR'}, "Zu wenige Korrespondenzen (Min 8).")
            return {'CANCELLED'}

        img_wh = None
        clip = context.edit_movieclip
        if clip:
            w, h = clip.size
            img_wh = (w, h)

        stats, state = promotion_step(
            A, B, img_wh, scene,
            lam=self.lambda_penalty,
            ransac_thresh=self.ransac_thresh
        )

        # Speichere aktuelles bestes Fit des aktiven Levels ins Overlay
        cur_lvl = state["current_level"]
        fit = None
        if cur_lvl in stats:
            fit = stats[cur_lvl]["fit"]
        if fit is not None:
            overlay["motion_model"] = {
                "type": cur_lvl,
                "M": fit["M"].tolist(),
                "rms": fit["rms"],
                "S": stats[cur_lvl]["S"],
                "inliers_count": int(np.sum(fit["inliers"])),
                "total": int(A.shape[0]),
                "inliers_mask": fit["inliers"].astype(bool).tolist(),
                "f0": f0, "f1": f1,
            }
        overlay["motion_model_stats"] = {k: {
            "S": v["S"], "rms": v["fit"]["rms"],
            "inliers": int(np.sum(v["fit"]["inliers"])),
            "rot": v.get("rot_deg"), "scale": v.get("scale"),
            "shear": v.get("shear_phi"), "parallax": v.get("parallax")
        } for k, v in stats.items()}

        if fit is not None:
            self.report({'INFO'}, f"Level: {state['current_level']} | S={overlay['motion_model']['S']:.3f} | Inliers={overlay['motion_model']['inliers_count']}/{overlay['motion_model']['total']}")
        else:
            self.report({'INFO'}, f"Level: {state['current_level']} (kein Fit gespeichert – zu wenige Inlier)")
        return {'FINISHED'}


def cleanup_overlay_draw():
    """Remove draw handler if active (called on addon unregister)."""
    global _draw_handle
    if _draw_handle is not None:
        try:
            bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
        except Exception:
            pass
        _draw_handle = None
