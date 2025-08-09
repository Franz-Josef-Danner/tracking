# tracking-efficent/Helper/split_tracks_segmented.py
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
                        'idx'      : 0,
                    })

        if not jobs:
            self.report({'INFO'}, "Keine Tracks mit mehreren Segmenten gefunden.")
            return {'CANCELLED'}

        self._jobs = jobs
        wm = context.window_manager
        self._timer = wm.event_timer_add(self._tick, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    # -------- Duplizieren (INVOKE + Ack + Fallback) --------
    def _dup_one(self, context, job):
        space = self._space
        orig = _track_by_name(space, job['orig_name'])
        if not orig:
            job['dup_needed'] = 0
            job['stage'] = 'trim'
            return

        tr = _tracks(space)
        before = {t.name for t in tr}
        self._dup_prev_names = before

        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            _select_only(space, orig)
            try:
                tr.active = orig
            except Exception:
                pass
            try:
                bpy.ops.clip.copy_tracks('INVOKE_DEFAULT')
                _ui_blink(context, swap=True)
                bpy.ops.clip.paste_tracks('INVOKE_DEFAULT')
                _ui_blink(context, swap=True)
            except Exception:
                pass

        self._dup_ack_until = time.time() + 1.0  # 1s

    def _dup_ack(self, context, job):
        space = self._space
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
                return True

        if time.time() < self._dup_ack_until:
            _ui_blink(context, swap=False)
            return False

        with context.temp_override(area=self._area, region=self._region, space_data=self._space):
            try:
                bpy.ops.clip.paste_tracks('EXEC_DEFAULT')
            except Exception:
                job['dup_needed'] = 0

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
        return True

    def _build_targets(self, job):
        names = [job['orig_name']] + job['dup_names']
        job['targets'] = names[:len(job['segments'])]
        job['stage'] = 'trim'
        job['idx'] = 0
        self._trim_target_idx = 0
        self._trim_phase = 'remain'

    # -------- Trimmen (INVOKE + Ack pro Schritt) --------
    def _trim_step(self, context, job):
        i = self._trim_target_idx
        if i >= len(job['targets']):
            return True

        space = self._space
        name = job['targets'][i]
        target = _track_by_name(space, name)
        if not target:
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
                self._trim_target_idx += 1
                self._trim_phase = 'remain'
                return False

    # -------- Modal-Tick --------
    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if not self._jobs:
            self._finish(context)
            self.report({'INFO'}, "Segment-Splitting abgeschlossen.")
            return {'FINISHED'}

        job = self._jobs[0]

        if job['stage'] == 'dup':
            if job['dup_needed'] > 0:
                if self._dup_ack_until == 0:
                    self._dup_one(context, job)
                else:
                    if self._dup_ack(context, job):
                        self._dup_ack_until = 0.0
                return {'RUNNING_MODAL'}
            else:
                self._build_targets(job)
                return {'RUNNING_MODAL'}

        if job['stage'] == 'trim':
            done = self._trim_step(context, job)
            if done:
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
