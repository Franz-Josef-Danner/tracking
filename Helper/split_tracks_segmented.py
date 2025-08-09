# Operator/split_tracks_segmented.py
import time
import bpy
from .process_marker_path import get_track_segments


def _find_clip_context(context):
    """Finde CLIP_EDITOR-Context (area, region, space)."""
    for area in context.screen.areas:
        if area.type == 'CLIP_EDITOR':
            for region in area.regions:
                if region.type == 'WINDOW':
                    return area, region, area.spaces.active
    return None, None, None


def _ui_blink(context, *, swap=False):
    """Gezielter UI-Refresh. swap=True für sichtbares Feedback."""
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP' if swap else 'DRAW', iterations=1)
    except Exception:
        pass
    try:
        bpy.context.view_layer.update()
    except Exception:
        pass


def _tracks(space):
    return space.clip.tracking.tracks


def _track_by_name(space, name):
    for t in _tracks(space):
        if t.name == name:
            return t
    return None


def _select_only(space, track):
    tr = _tracks(space)
    for t in tr:
        t.select = False
    if track:
        track.select = True


class CLIP_OT_split_tracks_segmented(bpy.types.Operator):
    """Teilt Tracks in eigenständige Segmente (Duplizieren → Trimmen), modal und deterministisch."""
    bl_idname = "clip.split_tracks_segmented"
    bl_label = "Split Tracks (Segmented, Modal)"
    bl_options = {'REGISTER', 'UNDO'}

    # --- interner State ---
    _area = _region = _space = None
    _timer = None

    # Arbeitsliste pro Track:
    # [{'orig_name': str, 'segments': [(s,e),...], 'dup_needed': int,
    #   'dup_names': [], 'targets': [], 'stage': 'dup'|'trim', 'idx': 0}]
    _jobs = None

    # Trimmen-Substate
    _trim_target_idx = 0
    _trim_phase = 'remain'  # 'remain' -> 'upto'

    # Duplizieren-Substate
    _dup_ack_until = 0.0
    _dup_prev_names = None

    # allgemeines Taktintervall
    _tick = 0.02

    @classmethod
    def poll(cls, context):
        a, r, s = _find_clip_context(context)
        return bool(s and s.clip)

    def invoke(self, context, event):
        self._area, self._region, self._space = _find_clip_context(context)
        if not self._space:
            self.report({'ERROR'}, "Kein CLIP_EDITOR aktiv.")
            return {'CANCELLED'}

        # Jobs vorbereiten: nur Tracks mit >=2 Segmenten
        jobs = []
        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            tr = _tracks(self._space)
            for t in tr:
                try:
                    segs = get_track_segments(t) or []
                except Exception:
                    segs = []
                if len(segs) >= 2:
                    jobs.append({
                        'orig_name': t.name,
                        'segments' : segs,
                        'dup_needed': max(0, len(segs) - 1),
                        'dup_names': [],
                        'targets'  : [],   # wird nach Duplizierung gefüllt
                        'stage'    : 'dup',
                        'idx'      : 0,    # für trim: Segment-/Target-Index
                    })

        if not jobs:
            self.report({'INFO'}, "Keine Tracks mit mehreren Segmenten gefunden.")
            return {'CANCELLED'}

        self._jobs = jobs
        wm = context.window_manager
        self._timer = wm.event_timer_add(self._tick, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _dup_one(self, context, job):
        """Starte eine Duplikation des Original-Tracks (INVOKE + Ack)."""
        space = self._space
        orig = _track_by_name(space, job['orig_name'])
        if not orig:
            # Original nicht gefunden → Job überspringen
            job['dup_needed'] = 0
            job['stage'] = 'trim'
            return

        tr = _tracks(space)
        before = {t.name for t in tr}
        self._dup_prev_names = before

        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            # Selektion/Active setzen
            _select_only(space, orig)
            try:
                tr.active = orig
            except Exception:
                pass

            # INVOKE → sichtbar
            try:
                bpy.ops.clip.copy_tracks('INVOKE_DEFAULT')
                _ui_blink(context, swap=True)
                bpy.ops.clip.paste_tracks('INVOKE_DEFAULT')
                _ui_blink(context, swap=True)
            except Exception:
                # kein harter Abbruch – wir probieren im Ack-Fenster EXEC-Fallback
                pass

        # Ack-Fenster öffnen
        self._dup_ack_until = time.time() + 1.0  # 1s max

    def _dup_ack(self, context, job):
        """Duplikations-Ack auswerten; bei Bedarf EXEC-Fallback."""
        space = self._space
        tr = _tracks(space)

        # Prüfen, ob neuer Name da ist
        after = {t.name for t in tr}
        new_names = list(after - (self._dup_prev_names or set()))

        if new_names:
            # neuen Track aufnehmen
            new = None
            for t in tr:
                if t.name in new_names:
                    new = t
                    break
            if new:
                job['dup_names'].append(new.name)
                job['dup_needed'] -= 1
                return True  # Duplizierung erledigt

        # timeout noch nicht erreicht → UI tick + weiter warten
        if time.time() < self._dup_ack_until:
            _ui_blink(context, swap=False)
            return False

        # EXEC-Fallback einmal versuchen
        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            try:
                bpy.ops.clip.paste_tracks('EXEC_DEFAULT')
            except Exception:
                # Fallback fehlgeschlagen – gebe auf (kein weiterer Versuch)
                job['dup_needed'] = 0

        # Nochmals prüfen
        tr = _tracks(space)
        after = {t.name for t in tr}
        new_names = list(after - (self._dup_prev_names or set()))
        if new_names:
            new = None
            for t in tr:
                if t.name in new_names:
                    new = t
                    break
            if new:
                job['dup_names'].append(new.name)
                job['dup_needed'] -= 1
        return True  # Ack-Phase abgeschlossen (egal ob erfolgreich oder nicht)

    def _build_targets(self, job):
        """Targets = [Original] + Kopien; Reihenfolge 1:1 zu Segmenten."""
        names = [job['orig_name']] + job['dup_names']
        job['targets'] = names[:len(job['segments'])]  # trimmen nur für vorhandene Ziele
        job['stage'] = 'trim'
        job['idx'] = 0
        self._trim_target_idx = 0
        self._trim_phase = 'remain'

    def _trim_step(self, context, job):
        """Ein Trimm-Teilschritt (remain oder upto) auf Ziel-Track i."""
        i = self._trim_target_idx
        if i >= len(job['targets']):
            # fertig getrimmt
            return True

        space = self._space
        name = job['targets'][i]
        target = _track_by_name(space, name)
        if not target:
            # Ziel existiert nicht mehr → weiter
            self._trim_target_idx += 1
            self._trim_phase = 'remain'
            return False

        s, e = job['segments'][i]

        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            _select_only(space, target)
            if self._trim_phase == 'remain':
                try:
                    context.scene.frame_set(e)
                    bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                                  action='REMAINED',
                                                  clear_active=False)
                    _ui_blink(context, swap=True)
                except Exception:
                    pass
                # nächste Phase für denselben Target
                self._trim_phase = 'upto'
                return False
            else:
                try:
                    context.scene.frame_set(s)
                    bpy.ops.clip.clear_track_path('INVOKE_DEFAULT',
                                                  action='UPTO',
                                                  clear_active=False)
                    _ui_blink(context, swap=True)
                except Exception:
                    pass
                # Target fertig → nächster
                self._trim_target_idx += 1
                self._trim_phase = 'remain'
                return False

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # keine Jobs mehr → Ende
        if not self._jobs:
            self._finish(context)
            self.report({'INFO'}, "Segment-Splitting abgeschlossen.")
            return {'FINISHED'}

        job = self._jobs[0]

        # Stage: Duplizieren
        if job['stage'] == 'dup':
            if job['dup_needed'] > 0:
                # Duplizierung läuft/ack
                if self._dup_ack_until == 0:
                    self._dup_one(context, job)
                else:
                    if self._dup_ack(context, job):
                        # Ack-Phase beendet → bereit für nächste Duplizierung
                        self._dup_ack_until = 0.0
                return {'RUNNING_MODAL'}
            else:
                # Targets bauen und zur Trim-Phase
                self._build_targets(job)
                return {'RUNNING_MODAL'}

        # Stage: Trimmen
        if job['stage'] == 'trim':
            done = self._trim_step(context, job)
            if done:
                # Job fertig → entfernen
                self._jobs.pop(0)
            return {'RUNNING_MODAL'}

        return {'RUNNING_MODAL'}

    def _finish(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
        self._timer = None

    def cancel(self, context):
        self._finish(context)
        self.report({'WARNING'}, "Segment-Splitting abgebrochen.")
