# Operator/clean_error_tracks.py
import bpy
import time

from ..Helper.grid_error_cleanup import grid_error_cleanup
from ..Helper.process_marker_path import get_track_segments
from ..Helper.clear_path_on_split_tracks_segmented import split_tracks_segmented_timed


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

def _ui_ping(context, text=None, *, swap=False):
    """Dezente UI-Aktualisierung + optional Statuszeile, ohne Redraw-Spam."""
    if text is not None:
        try:
            context.workspace.status_text_set(text)
        except Exception:
            pass
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP' if swap else 'DRAW', iterations=1)
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


# --- eigentlicher Operator ---------------------------------------------------

class CLIP_OT_clean_error_tracks(bpy.types.Operator):
    bl_idname = "clip.clean_error_tracks"
    bl_label = "Clean Error Tracks (Grid + ShortSegments + Timed Split)"
    bl_options = {'REGISTER', 'UNDO'}

    verbose: bpy.props.BoolProperty(
        name="Verbose log",
        default=False
    )

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.clip

    def _one_pass(self, context, area, region, space, *, do_split=True, split_delay_s=2.0):
        """
        Ein Cleanup-Pass:
          1) Grid-Error-Cleanup (einmal)
          2) Kurze Segmente entfernen + leere Tracks löschen
          3) Optional: segmentiertes Splitten (synchron EXEC_DEFAULT), aber zeitversetzt via Timer
        """
        wm     = context.window_manager
        clip   = space.clip
        tracks = clip.tracking.tracks

        # Progress (Grid=1, ShortSeg=1, Split=1 (Scheduling))
        steps_total = 3 if do_split else 2
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
        _ui_ping(context, f"Grid-Error-Cleanup fertig (gelöscht: {grid_deleted})", swap=True)

        # 2) Kurze Segmente löschen, dann leere Tracks entfernen
        try:
            _ui_ping(context, "Kurze Segmente löschen …")
            with context.temp_override(area=area, region=region, space_data=space):
                # a) Zu kurze Segmente entfernen (Schwelle: scene.frames_track)
                bpy.ops.clip.clean_short_tracks('EXEC_DEFAULT', action='DELETE_SEGMENTS')
                # b) Tracks ohne verbleibende Segmente entfernen (0-Frames)
                bpy.ops.clip.clean_tracks('EXEC_DEFAULT', frames=1, error=0.0, action='DELETE_TRACK')
            _ui_ping(context, "Short-Track-Cleanup abgeschlossen.", swap=True)
        except Exception as e:
            if self.verbose:
                print(f"[CleanShortTracks] übersprungen: {e}")

        step_idx += 1
        try:
            wm.progress_update(step_idx)
        except Exception:
            pass

        # 3) Optional: Segmentiertes Splitten – zeitversetzt (EXEC_DEFAULT + Timer)
        if do_split:
            original_tracks = _tracks_with_gaps(tracks)
            if original_tracks:
                try:
                    _ui_ping(context, "Segmentiertes Splitten wird zeitversetzt ausgeführt …")
                    with context.temp_override(area=area, region=region, space_data=space):
                        split_tracks_segmented_timed(
                            context, area, region, space,
                            original_tracks,
                            delay_seconds=split_delay_s
                        )
                    _ui_ping(context, f"Split-Schritte eingeplant (+{split_delay_s:.1f}s Takt).", swap=True)
                except Exception as e:
                    if self.verbose:
                        print(f"[TimedSplit] Scheduling fehlgeschlagen: {e}")

            step_idx += 1
            try:
                wm.progress_update(step_idx)
            except Exception:
                pass

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
        # Clip-Editor-Kontext suchen
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
                do_split=True,
                split_delay_s=2.0  # hier den Schritt-Takt anpassen (Sekunden)
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
