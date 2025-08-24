# Helper/bidirectional_track.py
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import bpy
from typing import List, Tuple, Dict, Optional
from mathutils import Vector

__all__ = ("CLIP_OT_bidirectional_track", "register", "unregister")

# Szene-Handshake-Keys (müssen zum Coordinator passen)
_BIDI_ACTIVE_KEY = "bidi_active"
_BIDI_RESULT_KEY = "bidi_result"


def _marker_at(track: bpy.types.MovieTrackingTrack, frame: int) -> Optional[bpy.types.MovieTrackingMarker]:
    """Robuste Marker-Abfrage (Blender API variiert beim exact-Param)."""
    try:
        return track.markers.find_frame(frame, exact=True)
    except TypeError:
        return track.markers.find_frame(frame)


def _clip_exec_ctx(context: bpy.types.Context) -> Optional[Dict]:
    """Erstellt einen gültigen Override-Kontext für Clip-Operatoren (Blender 4.x) und stellt sicher,
    dass space_data.clip gesetzt ist."""
    win = context.window
    scr = win.screen if win else None
    if not (win and scr):
        return None
    area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
    if not area:
        return None
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if not region:
        return None

    # Aktiven Space holen und Clip notfalls injizieren
    space = area.spaces.active
    if getattr(space, "clip", None) is None:
        try:
            if bpy.data.movieclips:
                space.clip = bpy.data.movieclips[0]
        except Exception:
            pass

    return {
        'window': win,
        'screen': scr,
        'area': area,
        'region': region,
        'space_data': space,
        'scene': context.scene,
    }


class CLIP_OT_bidirectional_track(bpy.types.Operator):
    """Frameweises Tracking mit kooperierenden Triplets (3 Marker je Position)."""
    bl_idname = "clip.bidirectional_track"
    bl_label = "Bidirectional Track (Triplet-Coop)"
    bl_options = {"REGISTER", "UNDO"}

    # Kompatibilitäts-Args (vom Coordinator gesetzt)
    use_cooperative_triplets: bpy.props.BoolProperty(  # type: ignore
        name="Cooperative Triplets",
        default=True,
    )
    auto_enable_from_selection: bpy.props.BoolProperty(  # type: ignore
        name="Only From Selection",
        default=True,
    )

    # interne Laufzeitdaten
    _timer: Optional[bpy.types.Timer] = None
    _groups: List[Tuple[bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack, bpy.types.MovieTrackingTrack]]
    _all_tracks: List[bpy.types.MovieTrackingTrack]
    _frame: int
    _frame_start: int
    _frame_end: int
    _override_ctx: Optional[Dict]

    def _log(self, msg: str) -> None:
        print(f"[BidiTriplet] {msg}")

    @classmethod
    def poll(cls, context):
        return getattr(context.area, "type", None) == "CLIP_EDITOR"

    def _select_only_groups(self):
        # Nur unsere Triplet-Tracks selektieren (alles andere deselektieren)
        for t in self._all_tracks:
            t.select = False
        for g in self._groups:
            for t in g:
                t.select = True

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        scn = context.scene
        scn[_BIDI_ACTIVE_KEY] = True
        scn[_BIDI_RESULT_KEY] = ""

        self._override_ctx = _clip_exec_ctx(context)

        # Clip aus dem Space des Overrides holen (nicht aus context.space_data!)
        space = (self._override_ctx or {}).get('space_data') if self._override_ctx else None
        clip = getattr(space, "clip", None) if space else None

        if not clip:
            self._log("ERROR: Kein MovieClip verfügbar.")
            scn[_BIDI_ACTIVE_KEY] = False
            scn[_BIDI_RESULT_KEY] = "NOOP"
            return {"CANCELLED"}

        # Tracks ermitteln (Active Object bevorzugen)
        tracking = clip.tracking
        if getattr(tracking, "objects", None) and tracking.objects:
            obj = tracking.objects.active or tracking.objects[0]
            tracks = obj.tracks
        else:
            tracks = tracking.tracks
        self._all_tracks = list(tracks)

        # Start-/Ende definieren
        self._frame = int(scn.frame_current)
        self._frame_start = int(getattr(clip, "frame_start", scn.frame_start))
        try:
            self._frame_end = int(clip.frame_start + clip.frame_duration - 1)
        except Exception:
            self._frame_end = int(scn.frame_end)

        # Kandidaten bestimmen
        consider = [t for t in self._all_tracks if (not self.auto_enable_from_selection) or getattr(t, "select", False)]

        # Selektion auf Kandidaten normalisieren
        for t in self._all_tracks:
            t.select = False
        for t in consider:
            t.select = True

        # Triplets am Startframe über identische Position (gerundet) erkennen
        pos_map: Dict[Tuple[int, int], List[bpy.types.MovieTrackingTrack]] = {}
        for t in consider:
            mk = _marker_at(t, self._frame)
            if not mk or getattr(mk, "mute", False):
                continue
            key = (int(round(mk.co[0] * 1000.0)), int(round(mk.co[1] * 1000.0)))
            pos_map.setdefault(key, []).append(t)

        self._groups = []
        for key, bucket in pos_map.items():
            if len(bucket) == 3:
                self._groups.append((bucket[0], bucket[1], bucket[2]))
                self._log(f"Triplet@{(key[0]/1000.0, key[1]/1000.0)}: {bucket[0].name}, {bucket[1].name}, {bucket[2].name}")
            elif len(bucket) > 3:
                # deterministische Dreier-Pakete bilden (Name sortiert)
                bucket_sorted = sorted(bucket, key=lambda t: t.name)
                for i in range(0, len(bucket_sorted), 3):
                    grp = bucket_sorted[i:i+3]
                    if len(grp) == 3:
                        self._groups.append((grp[0], grp[1], grp[2]))
                        self._log(f"Triplet(split)@{(key[0]/1000.0, key[1]/1000.0)}: {grp[0].name}, {grp[1].name}, {grp[2].name}")
                    else:
                        self._log(f"Skip unvollständige Restgruppe ({len(grp)}) @key={key}")

        if not self._groups:
            self._log(f"NOOP: Keine Triplets auf Frame {self._frame} gefunden.")
            scn[_BIDI_ACTIVE_KEY] = False
            scn[_BIDI_RESULT_KEY] = "NOOP"
            return {"CANCELLED"}

        # Modal starten
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.10, window=context.window)
        wm.modal_handler_add(self)
        self._log(f"Start bei Frame {self._frame}, Range=[{self._frame_start}..{self._frame_end}] | Triplets={len(self._groups)}")
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event):
        if event.type == "ESC":
            return self._finish(context, cancelled=True)
        if event.type != "TIMER":
            return {"PASS_THROUGH"}

        # Stop-Kriterien: keine Gruppen mehr oder Frame > Ende
        if not self._groups or self._frame >= self._frame_end:
            return self._finish(context, cancelled=False)

        scn = context.scene
        scn.frame_set(int(self._frame))

        # Pro Frame: jede Gruppe prüfen
        deactivated: List[int] = []
        for idx, (t0, t1, t2) in enumerate(self._groups):
            m0 = _marker_at(t0, self._frame)
            m1 = _marker_at(t1, self._frame)
            m2 = _marker_at(t2, self._frame)

            # Aktiv? (Marker vorhanden & nicht gemutet)
            if not (m0 and not m0.mute and m1 and not m1.mute and m2 and not m2.mute):
                # Spezifikation: Fällt einer aus → alle aus
                for trk, mk in ((t0, m0), (t1, m1), (t2, m2)):
                    if mk:
                        mk.mute = True
                    trk.select = False
                names = f"{t0.name}, {t1.name}, {t2.name}"
                self._log(f"Frame {self._frame}: '{names}' -> {int(bool(m0))+int(bool(m1))+int(bool(m2))}/3 aktiv → gesamte Gruppe deaktiviert.")
                deactivated.append(idx)
                continue

            # Alle 3 aktiv → Outlier mittig zu den beiden nächstliegenden setzen (kein Insert!)
            co0, co1, co2 = Vector(m0.co), Vector(m1.co), Vector(m2.co)
            d01 = (co0 - co1).length
            d02 = (co0 - co2).length
            d12 = (co1 - co2).length

            if d01 <= d02 and d01 <= d12:
                out_trk, out_mk = t2, m2
                A, B = co0, co1
                pair = (t0.name, t1.name)
            elif d02 <= d01 and d02 <= d12:
                out_trk, out_mk = t1, m1
                A, B = co0, co2
                pair = (t0.name, t2.name)
            else:
                out_trk, out_mk = t0, m0
                A, B = co1, co2
                pair = (t1.name, t2.name)

            mid = (A + B) * 0.5
            out_mk.co = (float(mid.x), float(mid.y))
            out_mk.is_keyed = True
            self._log(f"Frame {self._frame}: '{out_trk.name}' → midpoint({pair[0]}, {pair[1]}) = ({mid.x:.4f}, {mid.y:.4f})")

        # Deaktivierte Gruppen hinten beginnend löschen (Indices stabil halten)
        if deactivated:
            for i in sorted(deactivated, reverse=True):
                try:
                    self._groups.pop(i)
                except Exception:
                    pass

        # Wenn nach der Prüfung nichts mehr selektiert → fertig
        if not any(trk.select for grp in self._groups for trk in grp):
            self._log("Keine selektierten Marker mehr → Ende.")
            return self._finish(context, cancelled=False)

        # Genau EIN Tracking-Schritt vorwärts; nur unsere Triplet-Tracks selektiert
        self._select_only_groups()
        try:
            if self._override_ctx:
                bpy.ops.clip.track_markers(self._override_ctx, 'EXEC_DEFAULT', backwards=False, sequence=False)
            else:
                bpy.ops.clip.track_markers('EXEC_DEFAULT', backwards=False, sequence=False)
        except Exception as ex:
            self._log(f"WARN: track_markers failed: {ex!r}")
            # Ohne Tracking entstehen im nächsten Frame keine Marker → kontrolliertes Ende
            return self._finish(context, cancelled=True)

        # Nächster Frame
        if self._frame < self._frame_end:
            self._frame += 1
        else:
            return self._finish(context, cancelled=False)

        return {"RUNNING_MODAL"}

    def _finish(self, context: bpy.types.Context, *, cancelled: bool):
        scn = context.scene
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        scn[_BIDI_ACTIVE_KEY] = False
        scn[_BIDI_RESULT_KEY] = "CANCELLED" if cancelled else "FINISHED"
        self._log(f"DONE ({'CANCELLED' if cancelled else 'FINISHED'})")
        return {"CANCELLED" if cancelled else "FINISHED"}


def register():
    bpy.utils.register_class(CLIP_OT_bidirectional_track)


def unregister():
    bpy.utils.unregister_class(CLIP_OT_bidirectional_track)
