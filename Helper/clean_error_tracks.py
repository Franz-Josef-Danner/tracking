# file: operators/clean_error_tracks_modal.py
import bpy
from bpy.types import Operator
from bpy.props import BoolProperty

# --- deine bestehenden Helper (neu) ---
# Pfade ggf. an dein Paket anpassen:
from .clean_error_tracks_neu import _clip_override
from .multiscale_temporal_grid_clean import multiscale_temporal_grid_clean
from .segments import track_has_internal_gaps
from .mute_ops import mute_after_last_marker, mute_unassigned_markers
from .split_cleanup import clear_path_on_split_tracks_segmented, recursive_split_cleanup
from .clean_short_tracks import clean_short_tracks  # << neu gefordert

# Optionales HUD (Text im Clip-Editor zeichnen)
_draw_handle = None


def _deps_sync(context):
    deps = context.evaluated_depsgraph_get()
    deps.update()
    bpy.context.view_layer.update()
    context.scene.frame_set(context.scene.frame_current)


def _hud_draw(self, context):
    """Kleines HUD oben links im Clip-Editor."""
    import blf
    region = context.region
    if not region:
        return
    blf.size(0, 14, 72)
    x, y = 10, region.height - 22
    txt = f"Clean Error Tracks • Step {self._step_index+1}/{len(self._steps)}: {self._steps[self._step_index][0]}"
    blf.position(0, x, y, 0)
    blf.draw(0, txt)


class CLIP_OT_clean_error_tracks_modal(Operator):
    """Clean Error Tracks (modular, mit UI-Feedback)"""
    bl_idname = "clip.clean_error_tracks_modal"
    bl_label = "Clean Error Tracks (Modular UI)"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    show_hud: BoolProperty(
        name="HUD im Editor anzeigen",
        default=True,
        description="Zeigt den aktuellen Schritt als HUD im CLIP_EDITOR an",
    )

    def _set_status(self, txt):
        try:
            wm = bpy.context.window_manager
            wm.status_text_set(txt)
        except Exception:
            pass

    def _clear_status(self):
        try:
            bpy.context.window_manager.status_text_set(None)
        except Exception:
            pass

    def _progress_begin(self, total):
        self._progress_total = max(1, int(total))
        self._progress_cur = 0
        bpy.context.window_manager.progress_begin(0, self._progress_total)

    def _progress_update(self):
        self._progress_cur = min(self._progress_total, self._progress_cur + 1)
        bpy.context.window_manager.progress_update(self._progress_cur)

    def _progress_end(self):
        try:
            bpy.context.window_manager.progress_end()
        except Exception:
            pass

    # --- Schritt-Implementierungen -----------------------------------------

    def _step_prepare(self, context):
        """Kontext finden + initialer Sync."""
        self._ovr = _clip_override(context)
        if not self._ovr:
            self.report({'ERROR'}, "Kein CLIP_EDITOR-Kontext gefunden.")
            self._failed = True
            return
        with context.temp_override(**self._ovr):
            _deps_sync(context)
            self._clip = self._ovr["space_data"].clip
        self.report({'INFO'}, "Kontext bereit.")
        # Fortschritt
        self._progress_update()

    def _step_multiscale_clean(self, context):
        """Multiscale-Grid-Clean (wie neu.py)."""
        with context.temp_override(**self._ovr):
            scene = context.scene
            w, h = self._clip.size
            fr = (scene.frame_start, scene.frame_end)
            deleted = multiscale_temporal_grid_clean(
                context, self._ovr["area"], self._ovr["region"], self._ovr["space_data"],
                list(self._clip.tracking.tracks), fr, w, h,
                grid=(6, 6), start_delta=None, min_delta=3,
                outlier_q=0.90, hysteresis_hits=2, min_cell_items=4
            )
            self._deleted_any = deleted > 0
            _deps_sync(context)
        self.report({'INFO'}, f"Multiscale gelöscht: {int(self._deleted_any)} (bool).")
        self._progress_update()

    def _step_gap_split_recursive(self, context):
        """Gaps finden, duplizieren, segmentieren, rekursiv aufräumen."""
        with context.temp_override(**self._ovr):
            scene = context.scene
            tracks = self._clip.tracking.tracks
            original_tracks = [t for t in tracks if track_has_internal_gaps(t)]

            self._tracks_before = len(tracks)
            self._markers_before = sum(len(t.markers) for t in tracks)
            self._recursive_changed = False

            if not original_tracks:
                self.report({'INFO'}, "Keine internen Lücken – Split übersprungen.")
                _deps_sync(context)
                self._progress_update()
                return

            # Duplikate nur der Gap-Tracks
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
                context, self._ovr["area"], self._ovr["region"], self._ovr["space_data"],
                original_tracks, new_tracks
            )

            changed = recursive_split_cleanup(
                context, self._ovr["area"], self._ovr["region"], self._ovr["space_data"],
                tracks
            )
            if (isinstance(changed, bool) and changed) or (isinstance(changed, int) and changed > 0):
                self._recursive_changed = True

            # Leere Duplikate entsorgen
            empty_dupes = [t for t in new_tracks if len(t.markers) == 0]
            if empty_dupes:
                for t in tracks:
                    t.select = False
                for t in empty_dupes:
                    t.select = True
                bpy.ops.clip.delete_track()
                _deps_sync(context)

            self._tracks_after = len(tracks)
            self._markers_after = sum(len(t.markers) for t in tracks)
            self._progress_update()

    def _step_safety(self, context):
        """Safety-Passes (mute)."""
        with context.temp_override(**self._ovr):
            tracks = self._clip.tracking.tracks
            scene = context.scene
            mute_unassigned_markers(tracks)
            for t in tracks:
                mute_after_last_marker(t, scene.frame_end)
            _deps_sync(context)
        self.report({'INFO'}, "Safety-Passes abgeschlossen.")
        self._progress_update()

    def _step_final_short_clean(self, context):
        """Gewünschter finaler Short-Track-Cleanup (frames=scene.frames_track)."""
        with context.temp_override(**self._ovr):
            scene = context.scene
            try:
                clean_short_tracks(
                    context, action='DELETE_TRACK', frames=int(scene.get("frames_track", 25))
                )
                _deps_sync(context)
                self.report({'INFO'}, "Final: Short-Track-Cleanup ausgeführt.")
            except Exception as ex:
                self.report({'WARNING'}, f"Final clean_short_tracks fehlgeschlagen: {ex}")
        self._progress_update()

    # --- Modal-Maschine ------------------------------------------------------

    def invoke(self, context, event):
        # Schritte definieren (Name, Funktion)
        self._steps = [
            ("Prepare Context", self._step_prepare),
            ("Multiscale Clean", self._step_multiscale_clean),
            ("Gap Split & Recursive Cleanup", self._step_gap_split_recursive),
            ("Safety Passes", self._step_safety),
            ("Final Short Clean", self._step_final_short_clean),
        ]
        self._step_index = 0
        self._failed = False
        self._ovr = None
        self._clip = None

        # Progress starten
        self._progress_begin(len(self._steps))

        # Statusleiste
        self._set_status(f"{self.bl_label} – läuft …")

        # Optionales HUD
        global _draw_handle
        if self.show_hud:
            ovr = _clip_override(context)
            if ovr:
                area = ovr["area"]
                for region in area.regions:
                    if region.type == 'WINDOW':
                        _draw_handle = bpy.types.SpaceClipEditor.draw_handler_add(
                            _hud_draw, (self, context), 'WINDOW', 'POST_PIXEL'
                        )
                        break

        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self.report({'INFO'}, "Abgebrochen.")
            self._finish(context, cancelled=True)
            return {'CANCELLED'}

        if event.type == 'TIMER' or event.type == 'NONE':
            # pro Tick genau einen Schritt
            if self._step_index < len(self._steps) and not self._failed:
                name, fn = self._steps[self._step_index]
                try:
                    self._set_status(f"{self.bl_label} – {name} …")
                    fn(context)
                except Exception as ex:
                    self.report({'ERROR'}, f"Step '{name}' fehlgeschlagen: {ex}")
                    self._failed = True

                self._step_index += 1
                context.area.tag_redraw() if context.area else None
                return {'RUNNING_MODAL'}

            # Fertig oder fehlgeschlagen
            result = self._finish(context, cancelled=self._failed)
            return result

        return {'RUNNING_MODAL'}

    def _finish(self, context, cancelled=False):
        # UI aufräumen
        self._progress_end()
        self._clear_status()

        # HUD entfernen
        global _draw_handle
        if _draw_handle is not None:
            try:
                bpy.types.SpaceClipEditor.draw_handler_remove(_draw_handle, 'WINDOW')
            except Exception:
                pass
            _draw_handle = None

        # Abschlussmeldung
        if cancelled:
            return {'CANCELLED'}
        else:
            self.report({'INFO'}, "Clean Error Tracks – fertig.")
            return {'FINISHED'}
