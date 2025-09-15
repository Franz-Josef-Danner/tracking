# SPDX-License-Identifier: GPL-2.0-or-later
"""Helper/distanze.py
Distanz-Cleanup mit (a) Baseline-Klassifikation und (b) Schutz vor ko-lokalen Varianten.
"""

from __future__ import annotations
import bpy
from math import isfinite
from typing import Iterable, Set, Dict, Any, Optional, Tuple

# bestehende Imports/Utilities bleiben unverändert …

__all__ = ("run_distance_cleanup",)

# --- Logger Shim: Sicherung gegen fehlende log() Definition ---

try:
    log  # type: ignore[name-defined]
except NameError:
    def log(*_args, **_kwargs):
        return None

# ---------------------------------------------------------------------------
# Interne Hilfsfunktionen für Selbsterkennung (neu)
# ---------------------------------------------------------------------------
def _resolve_clip(context: bpy.types.Context) -> Optional[bpy.types.MovieClip]:
    scn = getattr(context, "scene", None)
    clip = getattr(context, "edit_movieclip", None)
    if not clip:
        space = getattr(context, "space_data", None)
        if space and getattr(space, "type", None) == "CLIP_EDITOR":
            clip = getattr(space, "clip", None)
    if not clip and scn:
        clip = getattr(scn, "clip", None)
    if not clip:
        try:
            clip = next(iter(bpy.data.movieclips))
        except Exception:
            clip = None
    return clip


def _marker_at_frame(track, frame: int):
    """Gibt den Marker eines Tracks exakt auf 'frame' zurück oder None."""
    try:
        for mk in track.markers:
            if int(getattr(mk, "frame", -1)) == int(frame):
                return mk
    except Exception:
        pass
    return None


def _track_marker_at_frame(
    tr: bpy.types.MovieTrackingTrack, frame: int
) -> Tuple[bool, Optional[bpy.types.MovieTrackingMarker]]:
    try:
        try:
            m = tr.markers.find_frame(int(frame), exact=True)
        except TypeError:
            m = tr.markers.find_frame(int(frame))
        return (m is not None), m
    except Exception:
        return (False, None)


def _find_clip_editor_context(context: bpy.types.Context, clip: bpy.types.MovieClip):
    """
    Liefert (window, area, region, space) für einen CLIP_EDITOR, falls vorhanden.
    Fällt ansonsten auf aktive window/screen zurück und setzt space_data pro Override.
    """
    win = getattr(context, "window", None)
    scr = getattr(win, "screen", None) if win else None
    area = None
    region = None
    space = None
    try:
        if scr:
            for a in scr.areas:
                if getattr(a, "type", "") == "CLIP_EDITOR":
                    area = a
                    # bevorzugt WINDOW-Region
                    for r in a.regions:
                        if getattr(r, "type", "") == "WINDOW":
                            region = r
                            break
                    space = next(
                        (s for s in a.spaces if getattr(s, "type", "") == "CLIP_EDITOR"),
                        None,
                    )
                    break
    except Exception:
        pass
    return win, area, region, space

def _collect_old_new_sets(
    context: bpy.types.Context,
    frame: int,
    *,
    require_selected_new: bool,
    include_muted_old: bool,
) -> Tuple[Set[int], Set[int], int, int]:
    """
    Liefert:
      - old_set: Pointer alter Tracks (Marker @frame nicht selektiert; gemutete optional)
      - new_set: Pointer neuer Tracks:
          * Wenn require_selected_new=True: Tracks, deren Marker @frame selektiert ist
          * Sonst: Tracks mit Marker @frame, die nicht gemutet sind
      - old_count_markers: Anzahl Referenzmarker @frame (ohne gemutete, wenn include_muted_old=False)
      - new_count_markers: Anzahl Marker @frame in new_set (für Log)
    """
    clip = _resolve_clip(context)
    if not clip:
        return set(), set(), 0, 0

    old_set: Set[int] = set()
    new_set: Set[int] = set()
    old_cnt = 0
    new_cnt = 0
    for tr in getattr(clip.tracking, "tracks", []):
        m = _marker_at_frame(tr, frame)
        if not m:
            continue
        ptr = int(tr.as_pointer())
        if require_selected_new:
            if bool(getattr(m, "select", False)):
                new_set.add(ptr)
                new_cnt += 1
            else:
                if include_muted_old or not bool(getattr(tr, "mute", False)):
                    old_set.add(ptr)
                    old_cnt += 1
        else:
            if include_muted_old or not bool(getattr(tr, "mute", False)):
                old_set.add(ptr)
                old_cnt += 1
            if not (getattr(m, "mute", False) or getattr(tr, "mute", False)):
                new_set.add(ptr)
                new_cnt += 1

    # Wichtig: „neu“ darf nicht gleichzeitig „alt“ sein, sonst ist die Differenz leer.
    old_set = old_set.difference(new_set)
    return old_set, new_set, old_cnt, new_cnt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_distance_cleanup(
    context: bpy.types.Context,
    *,
    baseline_ptrs: Optional[Set[int]] = None,
    frame: int,
    min_distance: Optional[float] = 200,
    distance_unit: str = "pixel",
    require_selected_new: bool = True,
    include_muted_old: bool = False,
    select_remaining_new: bool = True,
    verbose: bool = True,
    # NEU: Ko-location-Schutz (0-px/≈0-px Duplikate nicht entfernen)
    keep_zero_distance_duplicates: bool = True,
) -> Dict[str, Any]:
    """
    Klassifikation:
      • Mit ``baseline_ptrs``: "alt" = Tracks aus Baseline (Pointer ∈ baseline_ptrs) mit Marker @frame;
        "neu" = Tracks mit Marker @frame, deren Pointer nicht in ``baseline_ptrs`` enthalten sind.
        Selektion wird dabei ignoriert. (classification_mode="BASELINE_PTRS")
      • Ohne ``baseline_ptrs``: Selektion-basierte Klassifikation (Bestand).

    Ko-lokale Varianten:
      • Wenn ``keep_zero_distance_duplicates`` True ist, werden Kandidaten mit
        Mindestabstand ≤ ε (ε in Pixel; per Scene['kc_colocate_epsilon_px'] übersteuerbar,
        Default 0.75 px) nicht gelöscht.
    """
    clip = _resolve_clip(context)
    if not clip:
        return {"status": "NO_CLIP", "frame": frame}


    tracking = getattr(clip, "tracking", None)
    all_tracks = list(getattr(tracking, "tracks", []))

    # --- NEU: Entry-Log für schnelle Fehlerlokalisierung --------------------
    try:
        log(
            f"[DISTANZE] Enter: frame={int(frame)}, verbose={bool(verbose)}, "
            f"baseline_ptrs={0 if baseline_ptrs is None else len(baseline_ptrs)}, "
            f"keep_zero={bool(keep_zero_distance_duplicates)}"
        )
    except Exception:
        pass

    # --- Klassifikation: BASELINE_PTRS oder SELECTION_ONLY -------------------
    if baseline_ptrs:
        base_set = {int(p) for p in baseline_ptrs}
        old_tracks = []
        new_tracks = []
        for t in all_tracks:
            m = _marker_at_frame(t, frame)
            if not m:
                continue
            ptr = int(getattr(t, "as_pointer")())
            if ptr in base_set:
                # Alt nur, wenn Marker @frame vorhanden und (optional) nicht gemutet
                if include_muted_old or not (getattr(t, "mute", False) or getattr(m, "mute", False)):
                    old_tracks.append(t)
            else:
                # Neu = nicht in Baseline, Marker @frame vorhanden (Mute egal)
                new_tracks.append(t)
        classification_mode = "BASELINE_PTRS"
        try:
            log(
                f"[DISTANZE] Baseline active: size={len(base_set)} "
                f"sample={list(base_set)[:5]}"
            )
        except Exception:
            pass
    else:
        # Snapshot der Selektion (stabil gegenüber UI-Umschaltungen während des Laufs)
        new_tracks = []
        for t in all_tracks:
            m = _marker_at_frame(t, frame)
            # Neu = Marker-Selection ODER Track-Selection (Fallback für Detect)
            if m and (bool(getattr(m, "select", False)) or bool(getattr(t, "select", False))):
                new_tracks.append(t)

        old_tracks = []
        for t in all_tracks:
            m = _marker_at_frame(t, frame)
            if not m:
                continue  # kein Marker auf diesem Frame → irrelevant
            # Alt = weder Marker-Selection noch Track-Selection
            if not (bool(getattr(m, "select", False)) or bool(getattr(t, "select", False))):
                if include_muted_old or not bool(getattr(t, "mute", False)):
                    old_tracks.append(t)

        classification_mode = "SELECTION_ONLY"

    len_old_markers = len([_marker_at_frame(t, frame) for t in old_tracks])
    len_new_markers = len([_marker_at_frame(t, frame) for t in new_tracks])
    old_set = {int(t.as_pointer()) for t in old_tracks}
    new_set = {int(t.as_pointer()) for t in new_tracks}
    old_cnt_m = len_old_markers
    new_cnt_m = len_new_markers
    skipped_new_no_marker = 0
    log(
        f"[DISTANZE] Classification mode={classification_mode}; old={len_old_markers} new={len_new_markers}"
    )
    log(f"[DISTANZE] NewSet/OldSet ptr sizes: new={len(new_set)} old={len(old_set)}")
    log(
        f"[DISTANZE] Frame {frame}: old_markers={len_old_markers} new_markers={len_new_markers} skipped_new_no_marker=0"
    )

    # Mindestabstand: Wert aus Koordinator robust übernehmen (Fallback 200)
    auto_min_used = False
    scn = getattr(context, "scene", None)
    try:
        if min_distance is None:
            eff = None
            if scn is not None:
                # 1) Direkt vom Detect publizierter Wert (Single Source of Truth)
                eff_candidate = None
                try:
                    eff_candidate = scn.get("kc_detect_min_distance_px", None)
                except Exception:
                    eff_candidate = None
                if eff_candidate is not None:
                    try:
                        eff = float(eff_candidate)
                    except Exception:
                        eff = None
                    else:
                        auto_min_used = True
                        try:
                            log(
                                f"[DISTANZE] min_distance=None → scene['kc_detect_min_distance_px']={eff:.3f}"
                            )
                        except Exception:
                            pass
                # 2) Historischer Effective-Key als Fallback
                if eff is None:
                    eff_candidate = None
                    try:
                        eff_candidate = scn.get("kc_min_distance_effective", None)
                    except Exception:
                        eff_candidate = None
                    if eff_candidate is not None:
                        try:
                            eff = float(eff_candidate)
                        except Exception:
                            eff = None
                        else:
                            auto_min_used = True
                            try:
                                log(
                                    f"[DISTANZE] min_distance=None → scene['kc_min_distance_effective']={eff:.3f}"
                                )
                            except Exception:
                                pass
                # 3) Generische Defaults
                if eff is None:
                    eff_candidate = None
                    try:
                        eff_candidate = scn.get("min_distance_base", None)
                    except Exception:
                        eff_candidate = None
                    if eff_candidate is not None:
                        try:
                            eff = float(eff_candidate)
                        except Exception:
                            eff = None
                        else:
                            auto_min_used = True
                            try:
                                log(
                                    f"[DISTANZE] min_distance=None → scene['min_distance_base']={eff:.3f}"
                                )
                            except Exception:
                                pass
            if eff is None:
                md = 200.0
                auto_min_used = True
                try:
                    log("[DISTANZE] min_distance=None → fallback default=200.0")
                except Exception:
                    pass
            else:
                md = float(eff)
        else:
            md = float(min_distance)
        # Ungültige/negative Werte abfangen
        if not isfinite(md) or md <= 0.0:
            auto_min_used = True
            md = 200.0
            try:
                log("[DISTANZE] min_distance invalid/non-positive → fallback default=200.0")
            except Exception:
                pass
    except Exception:
        auto_min_used = True
        md = 200.0
        try:
            log("[DISTANZE] min_distance evaluation failed → fallback default=200.0")
        except Exception:
            pass
    min_distance = md
    log(
        f"[DISTANZE] run_distance_cleanup called: frame={frame}, min_distance={min_distance}, unit={distance_unit}, "
        f"require_selected_new={require_selected_new}, include_muted_old={include_muted_old}, "
        f"select_remaining_new={select_remaining_new}"
    )
    log(f"[DISTANZE] keep_zero={keep_zero_distance_duplicates}")
    log(
        f"[DISTANZE] Starting cleanup on frame {frame} with min_distance={min_distance} {distance_unit}; old tracks={len(old_tracks)}"
    )
    log(
        f"[DISTANZE] Found {len_old_markers} reference markers and {len(new_tracks)} new tracks to inspect."
    )

    # ======= Kern: Distanzprüfung & Löschung (new_set vs. old_set) =======
    removed = 0
    kept = 0
    checked = 0
    skipped_no_marker = 0
    skipped_unselected = 0
    failed_removals = 0
    zero_px_deletes = 0
    below_thr_nonzero_deletes = 0
    kept_zero_px = 0
    deleted_ptrs: list[int] = []

    # Referenz-Koordinaten (old_set) am Frame sammeln
    width = int(getattr(clip, "size", (0, 0))[0] or 0)
    height = int(getattr(clip, "size", (0, 0))[1] or 0)

    try:
        log(f"[DISTANZE] Clip size: {width}x{height} px")
    except Exception:
        pass

    # ε für Ko-location (Pixel)
    try:
        eps_px = float(getattr(context.scene, "kc_colocate_epsilon_px", 0.75))
        if not isfinite(eps_px) or eps_px <= 0.0:
            eps_px = 0.75
    except Exception:
        eps_px = 0.75

    try:
        log(f"[DISTANZE] Epsilon (colocate): eps_px={eps_px:.3f}")
    except Exception:
        pass
    ref_coords = []
    if width > 0 and height > 0:
        for tr in clip.tracking.tracks:
            try:
                ptr = int(tr.as_pointer())
                if ptr not in old_set:
                    continue
                ok, m = _track_marker_at_frame(tr, frame)
                if not ok or not m:
                    continue
                if not include_muted_old and (getattr(m, "mute", False) or getattr(tr, "mute", False)):
                    continue
                # Marker-Koordinaten sind normalized (0..1); für Pixelabstand später mit width/height skalieren
                ref_coords.append((float(m.co[0]), float(m.co[1])))
            except Exception:
                continue
    try:
        log(f"[DISTANZE] Reference coords collected: {len(ref_coords)}")
    except Exception:
        pass

    # Wenn keine Referenzen vorhanden sind, gibt es nichts zu vergleichen
    if not ref_coords or width == 0 or height == 0:
        log("[DISTANZE] No valid reference markers or clip size unknown; nothing to clean.")
        return {
            "status": "OK",
            "frame": frame,
            "removed": 0,
            "kept": 0,
            "checked_new": 0,
            "skipped_no_marker": 0,
            "skipped_unselected": 0,
            "min_distance": float(min_distance),
            "distance_unit": distance_unit,
            "old_count": int(len(old_set)),
            "new_total": int(len(new_set)),
            "auto_min_used": bool(auto_min_used),
            "deleted": [],
            "failed_removals": 0,
        }

    # Helper zur Pixel-Distanz
    def _px_dist(nco_a, nco_b) -> float:
        dx = (float(nco_a[0]) - float(nco_b[0])) * width
        dy = (float(nco_a[1]) - float(nco_b[1])) * height
        return (dx * dx + dy * dy) ** 0.5


    # Robuste Löschung via Operator + Verifikation; Fallback = Marker@Frame löschen
    def _delete_track_or_marker(
        tr: bpy.types.MovieTrackingTrack, ptr: int, frame_i: int
    ) -> Tuple[bool, str]:
        name = getattr(tr, "name", "<noname>")
        # 0) Context für CLIP_EDITOR finden
        win, area, region, space = _find_clip_editor_context(bpy.context, clip)
        # 1) Alles deselektieren, Ziel selektieren
        try:
            for _t in clip.tracking.tracks:
                _t.select = False
            tr.select = True
            ok_m, m = _track_marker_at_frame(tr, frame_i)
            if ok_m and m:
                try:
                    m.select = True
                except Exception:
                    pass
        except Exception as e:
            log(f"[DISTANZE]   pre-select failed for {name} ({ptr}): {e}")
        # 2) Operator-Aufruf mit Override
        try:
            override = {}
            if win:
                override["window"] = win
                override["screen"] = win.screen
            if area:
                override["area"] = area
            if region:
                override["region"] = region
            if space:
                override["space_data"] = space
            override["edit_movieclip"] = clip
            # bevorzugt den übergebenen Context, fällt andernfalls auf bpy.context zurück
            _ctx = context if hasattr(context, "temp_override") else bpy.context
            with _ctx.temp_override(**override):
                bpy.ops.clip.delete_track()
        except Exception as e:
            log(f"[DISTANZE]   bpy.ops.clip.delete_track() failed for {name} ({ptr}): {e}")
        # 3) Verifikation nach Operator
        try:
            still = False
            for _t in clip.tracking.tracks:
                if int(getattr(_t, "as_pointer")()) == ptr or getattr(_t, "name", "") == name:
                    still = True
                    break
            if not still:
                return True, "deleted:op"
        except Exception:
            pass
        # 4) Fallback: nur Marker am Frame löschen (nicht den ganzen Track)
        try:
            tr.markers.delete_frame(int(frame_i))
            try:
                m_chk = tr.markers.find_frame(int(frame_i), exact=True)
            except TypeError:
                m_chk = tr.markers.find_frame(int(frame_i))
            if not m_chk:
                return True, "deleted:marker"
        except Exception as e:
            log(f"[DISTANZE]   delete_frame(frame) failed for {name} ({ptr}): {e}")
        return False, "failed"

    # Vorab: mapping ptr->track für stabile Namenslogs auch nach evtl. Removals
    ptr_to_name = {}
    for _t in clip.tracking.tracks:
        try:
            ptr_to_name[int(getattr(_t, "as_pointer")())] = getattr(
                _t, "name", "<noname>"
            )
        except Exception:
            pass

    # WICHTIG: Snapshot der "neuen" selektierten Kandidaten anlegen,
    # damit require_selected_new NICHT vom späteren Deselektieren beeinflusst wird.
    _new_selected_snapshot = set(new_set) if require_selected_new else set()
    log(
        f"[DISTANZE] Selection snapshot: size={len(new_tracks)} "
        f"(require_selected_new={require_selected_new})"
    )

    # Iteration über neue Kandidaten
    # Achtung: Wir arbeiten über Kopie der Trackliste, da wir ggf. Tracks entfernen.
    for tr in list(clip.tracking.tracks):
        try:
            ptr = int(tr.as_pointer())
            if ptr not in new_set:
                continue

            ok, m_new = _track_marker_at_frame(tr, frame)
            if not ok or not m_new:
                skipped_no_marker += 1
                continue

            # Gating ausschließlich gegen den Snapshot, NICHT gegen aktuellen Select-Status
            if require_selected_new and (ptr not in _new_selected_snapshot):
                skipped_unselected += 1
                continue

            checked += 1
            nco = (float(m_new.co[0]), float(m_new.co[1]))

            # Mindestabstand gegen alle Referenzen prüfen
            too_close = False
            min_found = 1e12
            for rco in ref_coords:
                d = (
                    _px_dist(nco, rco)
                    if distance_unit == "pixel"
                    else ((nco[0] - rco[0]) ** 2 + (nco[1] - rco[1]) ** 2) ** 0.5
                )
                if d < min_found:
                    min_found = d
                if d < float(min_distance):
                    too_close = True
                    break

            name = ptr_to_name.get(ptr, getattr(tr, "name", "<noname>"))
            sel_state = f"Tsel={bool(getattr(tr,'select',False))}, Msel={bool(getattr(m_new,'select',False))}"

            # --- NEU: Borderline-Log bei knapper Unterschreitung/Überschreitung ---
            try:
                near_thr = float(min_distance) + float(eps_px)
                if (not too_close) and (min_found <= near_thr):
                    log(
                        f"[DISTANZE] NEAR ptr={ptr} name='{name}' d={min_found:.2f}px "
                        f"≈ thr+eps ({float(min_distance):.2f}+{float(eps_px):.2f}) @f{frame} ({sel_state})"
                    )
            except Exception:
                pass
            if too_close:
                # --- NEU: Ko-location-Schutz -----------------------------------
                # Kandidat liegt (nahezu) exakt auf einer Referenz → NICHT löschen.
                if keep_zero_distance_duplicates and (min_found <= float(eps_px)):
                    kept += 1
                    kept_zero_px += 1
                    log(
                        f"[DISTANZE] KEEP(COLOC) ptr={ptr} name='{name}' min_d={min_found:.3f}px ≤ eps={eps_px:.3f}px @f{frame} ({sel_state})"
                    )
                else:
                    ok_del, how = _delete_track_or_marker(tr, ptr, frame)
                    if ok_del:
                        removed += 1
                        deleted_ptrs.append(ptr)
                        if abs(min_found) < 1e-6:
                            zero_px_deletes += 1
                        else:
                            below_thr_nonzero_deletes += 1
                        log(
                            f"[DISTANZE]   DELETE  ptr={ptr} name='{name}' min_d={min_found:.2f}px @f{frame}  ({sel_state}) → {how}"
                        )
                    else:
                        failed_removals += 1
                        log(
                            f"[DISTANZE]   FAILED  ptr={ptr} name='{name}' min_d={min_found:.2f}px @f{frame}  ({sel_state}) → could not remove"
                        )
            else:
                kept += 1
                log(
                    f"[DISTANZE]   KEEP    ptr={ptr} name='{name}' min_d={min_found:.2f}px @f{frame}  ({sel_state})"
                )
        except Exception as e:
            # Defensive: Fehler pro Track nicht fatal
            log(f"[DISTANZE]   ERROR   ptr=? exception={e}")
            continue

    # Optional: Verbleibende neue selektieren (UI-Komfort; kein Gate)
    if select_remaining_new:
        for tr in clip.tracking.tracks:
            try:
                ptr = int(tr.as_pointer())
                if ptr not in new_set:
                    continue
                ok, m = _track_marker_at_frame(tr, frame)
                if not ok or not m:
                    continue
                tr.select = True
                try:
                    m.select = True
                except Exception:
                    pass
            except Exception:
                continue
        log(f"[DISTANZE] Reselect remaining new: done.")

    # Post-Verification: existieren gelöschte Pointer noch? + Ist-Zustand zählen
    still_present: list[Tuple[int, str]] = []
    marker_count_frame = 0
    try:
        for _t in clip.tracking.tracks:
            try:
                if _track_marker_at_frame(_t, frame)[0]:
                    marker_count_frame += 1
                p = int(getattr(_t, "as_pointer")())
                if p in deleted_ptrs:
                    still_present.append((p, getattr(_t, "name", "<noname>")))
            except Exception:
                pass
    except Exception:
        pass

    log(
        f"[DISTANZE] Cleanup complete: removed={removed}, kept={kept}, checked={checked}, "
        f"skipped_no_marker={skipped_no_marker}, skipped_unselected={skipped_unselected}, failed_removals={failed_removals}"
    )
    if still_present:
        log(
            f"[DISTANZE] WARNING: {len(still_present)} supposed-deleted tracks still present: {still_present[:10]}{' …' if len(still_present)>10 else ''}"
        )
    log(
        f"[DISTANZE] Post-frame stats @f{frame}: markers_at_frame={marker_count_frame}, deleted_ptrs={len(deleted_ptrs)}"
    )
    log(
        f"[DISTANZE] Reason breakdown @f{frame}: zero_px={zero_px_deletes}, "
        f"lt_thr_nonzero={below_thr_nonzero_deletes}, thr={min_distance}"
    )

    survivors = [ptr for ptr in new_set if ptr not in set(deleted_ptrs)]
    deleted_struct = [
        {"ptr": int(p), "track": ptr_to_name.get(p, None), "frame": int(frame)}
        for p in deleted_ptrs
    ]
    res = {
        "status": "OK",
        "frame": frame,
        "removed": int(removed),
        "kept": int(kept),
        "checked_new": int(checked),
        "skipped_no_marker": int(skipped_no_marker),
        "skipped_unselected": int(skipped_unselected),
        "min_distance": float(min_distance),
        "distance_unit": distance_unit,
        "old_count": int(len(old_set)),
        "new_total": int(len(new_set)),
        "auto_min_used": bool(auto_min_used),
        "deleted": deleted_struct,
        "new_ptrs_after_cleanup": survivors,
        "markers_at_frame": int(marker_count_frame),
        "kept_zero_px": int(kept_zero_px),
        "failed_removals": int(failed_removals),
    }
    try:
        log(
            f"[DISTANZE] Summary @f{frame}: mode={classification_mode}, "
            f"thr={float(min_distance):.2f}px, eps={float(eps_px):.2f}px, "
            f"old={len(old_set)}, new={len(new_set)}, "
            f"removed={res['removed']}, kept={res['kept']}, kept_coloc={res['kept_zero_px']}"
        )
    except Exception:
        pass
    return res
