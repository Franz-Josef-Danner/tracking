# SPDX-License-Identifier: GPL-2.0-or-later
"""
Utilities to reduce high-error tracks and inspect average reprojection error.
Provides run_reduce_error_tracks and get_avg_reprojection_error with diagnostic
logging.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import sys
import bpy
import time
try:
    # Einheitliche Fehler-Metrik wie in der Coordinator-Telemetrie
    from .count import error_value  # type: ignore
except Exception:
    # Fallback: lokale, schwächere Heuristik
    def error_value(track) -> float:
        try:
            v = float(getattr(track, "average_error", float("nan")))
            return v if (v == v and v >= 0.0) else -1.0
        except Exception:
            return -1.0

__all__ = ("run_reduce_error_tracks", "get_avg_reprojection_error")


def _name(tr):
    try:
        return getattr(tr, "name", "<noname>")
    except Exception:
        return "<ex>"


def _has_marker_on_frame(tr, frame):
    try:
        return any(m.frame == frame for m in tr.markers)
    except Exception:
        return False


def _peek_clip_context(ctx, clip):
    win = getattr(ctx, "window", None)
    scr = getattr(ctx, "screen", None)
    area_ok = region_ok = space_ok = False
    area_type = region_type = space_type = None
    has_clip_bound = False
    if win and scr:
        try:
            area = next((a for a in scr.areas if a.type == 'CLIP_EDITOR'), None)
            if area:
                area_ok = True
                area_type = area.type
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    region_ok = True
                    region_type = region.type
                space = area.spaces.active if hasattr(area, "spaces") else None
                if space:
                    space_ok = True
                    space_type = getattr(space, "type", None)
                    has_clip_bound = (getattr(space, "clip", None) == clip) and (clip is not None)
        except Exception:
            pass
    print(f"[CtxDBG] window={'Y' if win else 'N'} screen={'Y' if scr else 'N'} "
          f"area_ok={area_ok}({area_type}) region_ok={region_ok}({region_type}) "
          f"space_ok={space_ok}({space_type}) clip_bound={'Y' if has_clip_bound else 'N'}")


def _summarize_candidates(candidates, threshold_px, max_to_delete):
    total = len(candidates) if candidates else 0
    above = []
    top10 = []
    if candidates:
        above = [(t, e) for (t, e) in candidates if e is not None and e > threshold_px]
        try:
            top10 = sorted(above, key=lambda x: (x[1] if x[1] is not None else -1), reverse=True)[:10]
        except Exception:
            top10 = above[:10]
    print(
        f"[ReduceDBG] preselect: total={total} thr={threshold_px:.6f} above_thr={len(above)} "
        f"max_to_delete={max_to_delete}"
    )
    if top10:
        preview = [(_name(t), float(f"{e:.4f}") if e is not None else None) for (t, e) in top10]
        print(f"[ReduceDBG] preselect top10={preview}")
    return above


def _count_flags(tracks, frame_hint=None):
    sel = mut = hasf = 0
    for t in tracks:
        try:
            if getattr(t, "select", False):
                sel += 1
            if getattr(t, "mute", False):
                mut += 1
            if frame_hint is not None and _has_marker_on_frame(t, frame_hint):
                hasf += 1
        except Exception:
            pass
    return sel, mut, hasf


def _post_verify_exists(clip, target_names):
    try:
        remaining = []
        trk = getattr(clip, "tracking", None)
        tracks = getattr(trk, "tracks", None) if trk else None
        for name in target_names:
            try:
                if tracks and tracks.get(name):
                    remaining.append(name)
            except Exception:
                pass
        return remaining
    except Exception:
        return []

def _ensure_clip_context(context: bpy.types.Context) -> dict:
    """
    Liefert ein temp_override-Dict fuer den CLIP_EDITOR, damit bpy.ops.clip.* stabil laeuft.
    Faellt auf leeres Dict zurueck, wenn kein gueltiges Fenster/Area gefunden wird.
    """
    wm = bpy.context.window_manager
    if not wm:
        return {}
    for win in wm.windows:
        scr = getattr(win, 'screen', None)
        if not scr:
            continue
        for area in scr.areas:
            if area.type != 'CLIP_EDITOR':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active if hasattr(area, 'spaces') else None
            if region and space:
                return {
                    'window': win,
                    'area': area,
                    'region': region,
                    'space_data': space,
                    'scene': bpy.context.scene,
                }
    return {}



def _resolve_clip(context: bpy.types.Context):
    clip = getattr(getattr(context, "space_data", None), "clip", None)
    if not clip:
        clip = getattr(context, "edit_movieclip", None)
    if not clip and getattr(bpy.context, "edit_movieclip", None):
        clip = bpy.context.edit_movieclip
    return clip


def run_reduce_error_tracks(
    context: bpy.types.Context,
    *,
    max_to_delete: Optional[int] = None,
    object_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Löscht oder mutet Tracks mit hohem Fehlerwert.
    Erwartet Scene-Property 'error_track' als Schwellwert.
    Rückgabe enthält Diagnose-Felder für Telemetrie.
    """
    scn = context.scene
    thr = float(scn.get("error_track", 2.0))
    if max_to_delete is not None and max_to_delete <= 0:
        return {
            "deleted": 0,
            "names": [],
            "thr": thr,
            "policy": {
                "require_selected": bool(scn.get("reduce_only_selected", False)),
                "mute_instead_delete": bool(scn.get("reduce_mute_instead_delete", False)),
            },
            "candidates": [],
        }
    clip = _resolve_clip(context)
    trk = getattr(clip, "tracking", None) if clip else None
    tracks = list(getattr(trk, "tracks", [])) if trk else []

    cand: List[Tuple[str, float]] = []
    for t in tracks:
        try:
            if getattr(t, "mute", False):
                continue
            ev = float(error_value(t))
            if ev >= thr:
                cand.append((t.name, ev))
        except Exception:
            pass
    cand.sort(key=lambda x: x[1], reverse=True)
    print(f"[ReduceDBG] reducer candidates: count={len(cand)} top10={[(n, round(e,4)) for n,e in cand[:10]]}")
    _summarize_candidates(cand, thr, max_to_delete if max_to_delete is not None else 0)
    # Dynamische Default-Batchgröße, falls nicht vorgegeben:
    # 20 % der Kandidaten, min 5, max 50 (konservativ gegen Overkill)
    if max_to_delete is None:
        import math
        max_to_delete = max(5, min(50, math.ceil(len(cand) * 0.20)))

    require_selected = bool(scn.get("reduce_only_selected", False))
    if require_selected:
        cand = [(n, e) for (n, e) in cand if getattr(trk.tracks.get(n), "select", False)]
        print(f"[ReduceDBG] reducer policy: require_selected=True → remaining={len(cand)}")
    else:
        print(f"[ReduceDBG] reducer policy: require_selected=False")

    do_mute = bool(scn.get("reduce_mute_instead_delete", False))
    use_clean_tracks = bool(scn.get("reduce_use_clean_tracks", True)) and (not do_mute) and (not require_selected)
    print(f"[ReduceDBG] reducer action: {'MUTE' if do_mute else 'DELETE'} thr={thr} max_to_delete={max_to_delete}")

    deleted_names: List[str] = []
    count = 0
    k = min(int(max_to_delete), max(1, len(cand)))
    to_process = cand[:k]
    target_names = {name for name, _e in to_process}
    target_tracks = [trk.tracks.get(name) for name in target_names if trk and trk.tracks.get(name)]

    if target_names:
        print(f"[ReduceDBG] target snapshot(count={len(target_names)}): {list(target_names)}")
    try:
        sel_cnt, mut_cnt, hasf_cnt = _count_flags(target_tracks, frame_hint=None)
        print(f"[SelDBG] before-op: selected={sel_cnt} muted={mut_cnt} has_marker@frame_hint={hasf_cnt}")
    except Exception:
        pass

    _peek_clip_context(context, clip)
    _t0 = time.perf_counter()

    if do_mute:
        # — Variante: MUTE pro Track (kein Operator nötig)
        for name in list(target_names):
            t = trk.tracks.get(name) if trk else None
            if not t:
                continue
            try:
                t.mute = True
                deleted_names.append(name)
                count += 1
            except Exception as _exc:
                print(f"[ReduceDBG] reducer failed (mute) for {name}: {_exc}")
    elif use_clean_tracks:
        # — Variante: targeted DELETE via bpy.ops.clip.clean_tracks (ein Aufruf, kontext-sicher)
        # Ziel: genau k Top-Error-Tracks treffen, ohne Container mehrfach umzubauen.
        # 1) Schwelle zwischen k und k+1 (oder knapp unter err_k) berechnen
        errs_sorted = [e for (_n, e) in to_process]  # top-k errors (desc)
        err_k = float(errs_sorted[-1])  # kleinster der Top-K
        has_kp1 = len(cand) > k
        if has_kp1:
            err_kp1 = float(cand[k][1])  # erster nach den Top-K
            thr_clean = 0.5 * (err_k + err_kp1)  # Midpoint trennt exakt K vs. K+1 (bei !=)
        else:
            thr_clean = err_k - 1e-6  # knapp darunter → trifft nur Top-K
        print(f"[ReduceDBG] clean_tracks threshold -> {thr_clean:.6f} (err_k={err_k:.6f}{' err_k+1='+str(err_kp1) if has_kp1 else ''})")
        # 2) Operator im CLIP-Override aufrufen
        try:
            override = _ensure_clip_context(context)
            if override:
                with bpy.context.temp_override(**override):
                    bpy.ops.clip.clean_tracks(frames=0, error=float(thr_clean), action='DELETE_TRACK')
            else:
                bpy.ops.clip.clean_tracks(frames=0, error=float(thr_clean), action='DELETE_TRACK')
        except Exception as _op_exc:
            print(f"[ReduceDBG] operator clean_tracks failed: {_op_exc}")
        # 3) Ergebnis prüfen (Namen, Count)
        try:
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            # Alle, die vorab >= thr_clean lagen (d.h. Zielmenge), als gelöscht zählen
            goal_set = {n for (n, e) in cand if e >= thr_clean}
            for name in list(goal_set):
                still_there = bool(trk.tracks.get(name)) if trk else False
                if not still_there:
                    deleted_names.append(name)
            count = len(deleted_names)
        except Exception as _chk_exc:
            print(f"[ReduceDBG] post-clean_tracks check failed: {_chk_exc}")
        # Hinweis: Bei gleichen Fehlerwerten um err_k kann es >k werden (Tie-Case).
        if count > k:
            print(f"[ReduceDBG] NOTE: deleted={count} > k={k} (ties at threshold)")
    else:
        # — Variante: DELETE via Operator (kontext-sicher)
        # 1) Auswahl vorbereiten
        try:
            for t in tracks:
                try:
                    t.select = False
                except Exception:
                    pass
            for t in tracks:
                if t.name in target_names:
                    try:
                        t.select = True
                    except Exception:
                        pass
        except Exception as _sel_exc:
            print(f"[ReduceDBG] selection prep failed: {_sel_exc}")
        # 2) Operator aufrufen (mit Override, falls möglich)
        op_ok = False
        try:
            override = _ensure_clip_context(context)
            if override:
                with bpy.context.temp_override(**override):
                    bpy.ops.clip.delete_track()
            else:
                bpy.ops.clip.delete_track()
            op_ok = True
        except Exception as _op_exc:
            print(f"[ReduceDBG] operator delete_track failed: {_op_exc}")
        # 3) Ergebnis prüfen & zählen; ggf. Fallback auf MUTE
        try:
            # Layer refresh, dann Existenz prüfen
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
            for name in list(target_names):
                still_there = bool(trk.tracks.get(name)) if trk else False
                if not still_there:
                    deleted_names.append(name)
                    count += 1
        except Exception as _chk_exc:
            print(f"[ReduceDBG] post-delete check failed: {_chk_exc}")
        # Falls der Operator nichts gelöscht hat, auf MUTE ausweichen (damit der Zyklus vorankommt).
        if count == 0:
            print("[ReduceDBG] operator deletion had no effect -> fallback to MUTE for targets")
            for name in list(target_names):
                t = trk.tracks.get(name) if trk else None
                if not t:
                    continue
                try:
                    t.mute = True
                    deleted_names.append(name)
                    count += 1
                except Exception as _exc:
                    print(f"[ReduceDBG] reducer failed (mute-fallback) for {name}: {_exc}")
    _t1 = time.perf_counter()
    print(f"[TimeDBG] reduce pass wall={( _t1 - _t0 ) * 1000:.2f}ms")
    try:
        remaining = _post_verify_exists(clip, target_names)
        kept = len(remaining)
        removed = len(target_names) - kept
        if target_names:
            rem_names = remaining
            print(
                f"[VerifyDBG] post-op: expected_remove={len(target_names)} → removed={removed} kept={kept} kept_names={rem_names}"
            )
        else:
            print("[VerifyDBG] post-op: no targets snapshot (nothing to verify)")
    except Exception as ex:
        print(f"[VerifyDBG] post-op verification failed: {ex!r}")
    print(f"[ReduceDBG] reducer summary: affected={count}")
    return {
        "deleted": count,  # Anzahl betroffener Tracks (deleted oder mute-fallback)
        "names": deleted_names,
        "thr": thr,
        "policy": {
            "require_selected": require_selected,
            "mute_instead_delete": do_mute,
            "use_clean_tracks": use_clean_tracks,
        },
        "candidates": cand[:50],
    }


def get_avg_reprojection_error(context):
    """
    Durchschnittlicher Reprojektion-Error nur über Frames mit vorhandener Kamera.
    Gibt None zurück, wenn keine gültige Rekonstruktion oder keine Punkte.
    """
    clip = getattr(context, "edit_movieclip", None)
    if not clip or not getattr(clip, "tracking", None):
        return None
    obj   = clip.tracking.objects.active if clip.tracking.objects else None
    recon = getattr(obj, "reconstruction", None)
    if not recon or not getattr(recon, "is_valid", False):
        return None

    cam_frames = set()
    try:
        for cam in getattr(recon, "cameras", []):
            try:
                cam_frames.add(int(getattr(cam, "frame", -1)))
            except Exception:
                pass
    except Exception:
        return None
    if not cam_frames:
        return None

    fmin, fmax = min(cam_frames), max(cam_frames)
    total_err = 0.0
    total_cnt = 0

    try:
        tracks = clip.tracking.tracks
        for tr in tracks:
            for mk in getattr(tr, "markers", []):
                f = int(getattr(mk, "frame", -1))
                if f < fmin or f > fmax or f not in cam_frames:
                    continue
                err = getattr(mk, "reprojection_error", None)
                if err is None:
                    continue
                total_err += float(err)
                total_cnt += 1
    except Exception:
        return None

    if total_cnt == 0:
        return None
    return total_err / total_cnt
