def run_clean_error_tracks(context, *, show_popups: bool = False, soften: float = 0.5):
    """
    Führt Clean Error Tracks mit sichtbaren UI-Schritten aus.
    Der Parameter `soften` (0..1) reduziert die Lösch-Aggressivität:
      0.0 = maximal weich (löscht am wenigsten)
      0.5 = ca. halb so aggressiv (Standard)
      1.0 = ursprüngliches Verhalten
    Rückgabe: {'FINISHED'} oder {'CANCELLED'}.
    """
    soften = max(0.0, min(soften, 1.0))  # clamp
    scene = context.scene
    wm = context.window_manager
    ovr = _clip_override(context)
    if not ovr:
        if show_popups:
            wm.popup_menu(
                lambda self, ctx: self.layout.label(text="Kein CLIP_EDITOR-Kontext gefunden."),
                title="Clean Error Tracks", icon='CANCEL'
            )
        print("[CleanError] ERROR: Kein gültiger CLIP_EDITOR-Kontext gefunden.")
        return {'CANCELLED'}

    # Fortschritt vorbereiten (5 Hauptschritte)
    steps_total = 5
    try:
        wm.progress_begin(0, steps_total)
    except Exception:
        pass

    def step_update(i, label):
        _status(wm, f"Clean Error Tracks – {label} ({i}/{steps_total})")
        try:
            wm.progress_update(i)
        except Exception:
            pass
        _pulse_ui()

    # ---------- 1) PREPARE ----------
    step_update(1, "Prepare")
    with context.temp_override(**ovr):
        _deps_sync(context)
        clip = ovr["space_data"].clip
        if not clip:
            if show_popups:
                wm.popup_menu(lambda self, ctx: self.layout.label(text="Kein aktiver Clip."),
                              title="Clean Error Tracks", icon='CANCEL')
            print("[CleanError] ERROR: Kein aktiver Clip.")
            _status(wm, None)
            try:
                wm.progress_end()
            except Exception:
                pass
            return {'status': 'CANCELLED'}

    # ---------- 2) MULTISCALE CLEAN (weicher) ----------
    step_update(2, "Multiscale Clean")
    with context.temp_override(**ovr):
        w, h = clip.size
        fr = (scene.frame_start, scene.frame_end)

        # Weichheits-Mapping:
        # - Je kleiner soften, desto weniger wird gelöscht.
        # - Wir erhöhen outlier_q, hysteresis_hits und min_cell_items leicht,
        #   und vergrößern min_delta minimal. Bei soften=1.0 landen wir nahe Original.
        # Ursprünglich: outlier_q=2, hysteresis_hits=2, min_cell_items=4, min_delta=3
        outlier_q = 2 + (1 if soften <= 0.75 else 0) + (1 if soften <= 0.25 else 0)
        hysteresis_hits = 2 + (1 if soften <= 0.75 else 0)
        min_cell_items = 4 + (2 if soften <= 0.5 else 1 if soften < 1.0 else 0)
        min_delta = 3 + (1 if soften <= 0.5 else 0)

        deleted = multiscale_temporal_grid_clean(
            context, ovr["area"], ovr["region"], ovr["space_data"],
            list(clip.tracking.tracks), fr, w, h,
            grid=(6, 6), start_delta=None, min_delta=min_delta,
            outlier_q=outlier_q, hysteresis_hits=hysteresis_hits, min_cell_items=min_cell_items
        )
        print(f"[MultiScale] (soften={soften:.2f}) params: "
              f"outlier_q={outlier_q}, hysteresis_hits={hysteresis_hits}, "
              f"min_cell_items={min_cell_items}, min_delta={min_delta} | deleted: {deleted}")
        _deps_sync(context)

    # ---------- 3) GAP SPLIT + RECURSIVE ----------
    with context.temp_override(**ovr):
        tracks_global_before = len(clip.tracking.tracks)
        markers_global_before = sum(len(t.markers) for t in clip.tracking.tracks)

    step_update(3, "Gap Split & Recursive Cleanup")
    with context.temp_override(**ovr):
        tracks = clip.tracking.tracks
        original_tracks = [t for t in tracks if track_has_internal_gaps(t)]

        tracks_before = len(tracks)
        markers_before = sum(len(t.markers) for t in tracks)
        deleted_any = deleted > 0
        recursive_changed = False

        if not original_tracks:
            msg = "Keine Tracks mit internen Lücken – Split übersprungen."
            print(f"[CleanError] {msg}")
            if show_popups:
                wm.popup_menu(lambda self, ctx, m=msg: self.layout.label(text=m),
                              title="Clean Error Tracks", icon='INFO')
        else:
            existing_names = {t.name for t in tracks}
            for t in tracks:
                t.select = False
            for t in original_tracks:
                t.select = True

            bpy.ops.clip.copy_tracks()
            bpy.ops.clip.paste_tracks()
            _deps_sync(context)

            all_names_after = {t.name for t in tracks}
            new_names = all_names_after - existing_names
            new_tracks = [t for t in tracks if t.name in new_names]

            clear_path_on_split_tracks_segmented(
                context, ovr["area"], ovr["region"], ovr["space_data"],
                original_tracks, new_tracks
            )

            # Hinweis: Falls recursive_split_cleanup intern sehr aggressiv ist,
            # könnte man hier optional einen "softer mode" per globalem Flag implementieren.
            changed_in_recursive = recursive_split_cleanup(
                context, ovr["area"], ovr["region"], ovr["space_data"],
                tracks
            )
            if (isinstance(changed_in_recursive, bool) and changed_in_recursive) or \
               (isinstance(changed_in_recursive, int) and changed_in_recursive > 0):
                recursive_changed = True

            # Leere Duplikate entsorgen (neutral)
            empty_dupes = [t for t in new_tracks if len(t.markers) == 0]
            if empty_dupes:
                for t in tracks:
                    t.select = False
                for t in empty_dupes:
                    t.select = True
                bpy.ops.clip.delete_track()
                _deps_sync(context)

        tracks_after = len(tracks)
        markers_after = sum(len(t.markers) for t in tracks)
        made_changes = bool(
            deleted_any or
            (tracks_after != tracks_before) or
            (markers_after != markers_before) or
            recursive_changed
        )
        print(f"[CleanError] Changes? {made_changes} | "
              f"tracks: {tracks_before}->{tracks_after} | "
              f"markers: {markers_before}->{markers_after} | "
              f"recursive_changed={recursive_changed}")

    # ---------- 4) SAFETY ----------
    step_update(4, "Safety Passes")
    with context.temp_override(**ovr):
        tracks = clip.tracking.tracks
        for t in tracks:
            mute_after_last_marker(t, scene.frame_end)
        mute_unassigned_markers(tracks)
        _deps_sync(context)

    # ---------- 5) FINAL SHORT CLEAN (weicher) ----------
    step_update(5, "Final Short Clean")
    with context.temp_override(**ovr):
        from .clean_short_tracks import clean_short_tracks as _short
        scn = context.scene

        prev_skip = bool(scn.get("__skip_clean_short_once", False))
        try:
            scn["__skip_clean_short_once"] = False

            # Ursprünglich: frames = getattr(scn, "frames_track", 25)
            base_frames = int(getattr(scn, "frames_track", 25) or 25)

            # Weicher: je kleiner soften, desto kleiner die Mindestlänge -> weniger Löschungen.
            # soften=0.5 => ~halbe Mindestlänge.
            frames_eff = max(5, int(round(base_frames * max(0.1, soften))))

            print(f"[ShortClean] base_frames={base_frames} -> frames_eff={frames_eff} (soften={soften:.2f})")

            _short(
                context,
                min_len=frames_eff,
                action="DELETE_TRACK",   # beibehalten; Reduktion erfolgt über min_len
                respect_fresh=True,
                verbose=True,
            )
        finally:
            scn["__skip_clean_short_once"] = prev_skip

        _deps_sync(context)

    # ---------- Abschluss ----------
    if show_popups:
        wm.popup_menu(lambda self, ctx: self.layout.label(text="Abgeschlossen."),
                      title="Clean Error Tracks", icon='CHECKMARK')

    _status(wm, None)
    try:
        wm.progress_end()
    except Exception:
        pass

    with context.temp_override(**ovr):
        tracks_global_after = len(clip.tracking.tracks)
        markers_global_after = sum(len(t.markers) for t in clip.tracking.tracks)

    deleted_tracks_global = max(0, tracks_global_before - tracks_global_after)
    deleted_markers_global = max(0, markers_global_before - markers_global_after)
    deleted_any_global = (deleted_tracks_global > 0) or (deleted_markers_global > 0)

    result = {
        'status': 'FINISHED',
        'deleted_any': bool(deleted_any_global),
        'deleted_tracks': int(deleted_tracks_global),
        'deleted_markers': int(deleted_markers_global),
        'multiscale_deleted': int(deleted),
        'changes_step3': bool(made_changes),
        'tracks_before': int(tracks_global_before),
        'tracks_after': int(tracks_global_after),
        'markers_before': int(markers_global_before),
        'markers_after': int(markers_global_after),
        'soften': float(soften),
    }
    print(f"[CleanError] SUMMARY: {result}")
    return result
