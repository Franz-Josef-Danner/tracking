# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.grid_error_cleanup import grid_error_cleanup
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import clear_path_on_split_tracks_segmented


# --- kleine Helfer -----------------------------------------------------------

def _count_all_markers(tracks):
    """Zählt alle Marker über alle Tracks hinweg."""
    return sum(len(getattr(t, "markers", [])) for t in tracks)

def _tracks_with_gaps(tracks):
    """Tracks mit >= 2 Segmenten (interne Lücken) finden."""
    out = []
    for t in tracks:
        try:
            segs = get_track_segments(t)
        except Exception:
            segs = []
        if len(segs) >= 2:
            out.append(t)
    return out

def _duplicate_selected_tracks(context, area, region, space):
    """Selektierte Tracks duplizieren, UI kurz aktualisieren."""
    with context.temp_override(area=area, region=region, space_data=space):
        bpy.ops.clip.copy_tracks()
        bpy.ops.clip.paste_tracks()
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
        context.scene.frame_set(context.scene.frame_current)
        bpy.context.view_layer.update()
        time.sleep(0.03)

def _ui_ping(context, text=None, redraw_iters=1):
    """Kleine UI-Aktualisierung + optional Statuszeile."""
    wm = context.window_manager
    if text is not None:
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=redraw_iters)
    except Exception:
        pass
    bpy.context.view_layer.update()


# --- eigentlicher Operator ---------------------------------------------------

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid + optional Split)"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: bpy.props.BoolProperty(
        name="Verbose log",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, *, do_split=False):
        """
        Ein Cleanup-Pass:
          1) Grid-Error-Cleanup (einmal)
          2) Optional (nur in diesem Pass): Lücken-Tracks duplizieren & splitten
        """
        wm     = context.window_manager
        clip   = space.clip
        tracks = clip.tracking.tracks

        # Progress-Setup (1 Schritt Grid + ggf. 1 Schritt Split)
        original_tracks = _tracks_with_gaps(tracks) if do_split else []
        steps_total = 1 + (1 if (do_split and original_tracks) else 0)
        step_idx = 0
        try:
            wm.progress_begin(0, steps_total)
        except Exception:
            pass

        before_total = _count_all_markers(tracks)

        # 1) Grid-Error-Cleanup
        _ui_ping(context, "Grid-Error-Cleanup läuft …")
        grid_deleted = 0
        try:
            grid_deleted = grid_error_cleanup(context, space, verbose=self.verbose)
        except Exception as e:
            if self.verbose:
                print(f"[GridError] übersprungen: {e}")
        step_idx += 1
        try:
            wm.progress_update(step_idx)
        except Exception:
            pass
        _ui_ping(context, f"Grid-Error-Cleanup fertig (gelöscht: {grid_deleted})")

        # Kurze Segmente löschen, dann leere Tracks entfernen
        try:
            _ui_ping(context, "Kurze Segmente löschen …")
            with context.temp_override(area=area, region=region, space_data=space):
                # 1) Zu kurze Segmente entfernen (Schwelle: scene.frames_track)
                bpy.ops.clip.clean_short_tracks('EXEC_DEFAULT', action='DELETE_SEGMENTS')
                # 2) Tracks ohne verbleibende Segmente entfernen (0-Frames)
                bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=1, error=0.0, action='DELETE_TRACK')
            _ui_ping(context, "Short-Track-Cleanup abgeschlossen.")
        except Exception as e:
            if self.verbose:
                print(f"[CleanShortTracks] übersprungen: {e}")

        # 2) Optional Split der Gaps – wiederholt, bis keine Gaps mehr oder keine Reduktion
        if do_split:
            # >>> CHANGE START: Split-Loop mit Konvergenz-Check + Failsafe
            max_loops = 10
            prev_gap_set = set()

            for _ in range(max_loops):
                # Tracks mit Lücken frisch ermitteln
                original_tracks = _tracks_with_gaps(tracks)
                if not original_tracks:
                    break

                gap_set = {t.name for t in original_tracks}
                # Keine Fortschritte seit letztem Durchlauf → abbrechen
                if gap_set == prev_gap_set:
                    if self.verbose:
                        print("[SplitLoop] keine weitere Reduktion der Gaps – breche ab.")
                    break
                prev_gap_set = gap_set

                _ui_ping(context, "Split von Tracks mit Lücken …")
                existing_names = {t.name for t in tracks}

                # Auswahl vorbereiten
                for t in tracks:
                    t.select = False
                for t in original_tracks:
                    t.select = True

                # Duplizieren der ausgewählten Tracks
                _duplicate_selected_tracks(context, area, region, space)

                # neue Duplikate bestimmen
                all_names = {t.name for t in tracks}
                new_names = all_names - existing_names
                new_tracks = [t for t in tracks if t.name in new_names]

                if not new_tracks:
                    # Nichts dupliziert → keine weitere Arbeit
                    break

                # Pfade entsprechend Segmenten beschneiden
                clear_path_on_split_tracks_segmented(
                    context, area, region, space,
                    original_tracks, new_tracks
                )

                # Progress & UI
                step_idx += 1
                try:
                    wm.progress_update(min(step_idx, steps_total))
                except Exception:
                    pass
                _ui_ping(context, "Split abgeschlossen.")
            # >>> CHANGE END

        after_total = _count_all_markers(tracks)
        changed = int(grid_deleted)

        if self.verbose:
            print(f"[Cleanup] grid_deleted={grid_deleted}, "
                  f"markers_before={before_total}, markers_after={after_total}, changed={changed}")

        try:
            wm.progress_end()
        except Exception:
            pass

        return changed

    def execute(self, context):
        # Clip-Editor-Kontext suchen (sonst poll fail)
        clip_area = clip_region = clip_space = None
        for area in context.screen.areas:
            if area.type == 'CLIP_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        clip_area = area
                        clip_region = region
                        clip_space = area.spaces.active
                        break

        if not clip_space:
            self.report({'ERROR'}, "Kein gültiger CLIP_EDITOR-Kontext gefunden.")
            return {'CANCELLED'}

        wm = context.window_manager
        # Busy-Cursor + Status während der Laufzeit
        try:
            context.window.cursor_modal_set('WAIT')
        except Exception:
            pass
        try:
            context.workspace.status_text_set("Error-Cleanup gestartet …")
        except Exception:
            pass

        try:
            changed = self._one_pass(
                context,
                clip_area, clip_region, clip_space,
                do_split=True
            )
        finally:
            # UI aufräumen
            try:
                context.workspace.status_text_set(None)
            except Exception:
                pass
            try:
                context.window.cursor_modal_restore()
            except Exception:
                pass

        if self.verbose:
            print(f"[Cleanup] single pass finished, changed={changed}")

        self.report({'INFO'}, f"Cleanup beendet. Änderungen: {changed}")
        return {'FINISHED'}
