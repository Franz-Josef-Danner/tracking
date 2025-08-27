# Blender Parallax Keyframe Helper
# Vorschläge für Keyframe A/B basierend auf Parallax in 2D-Trackdaten
# PEP 8-konform, kommentiert. Für Blender 3.x/4.x.

import bpy
import math
import time
from collections import defaultdict
from mathutils import Vector

# ----------------------------- Einstellungen ---------------------------------

# Mindestabstand (Frames) zwischen Keyframe A und B
MIN_FRAME_GAP = 25

# Wie viele Top-Paare ausgeben?
TOP_K = 10

# Mindestanzahl gemeinsamer Tracks, damit ein Paar gewertet wird
MIN_COMMON_TRACKS = 12

# Schrittweite beim Scannen (1 = alle Frames; höher = schneller, grober)
FRAME_STEP = 2

# Optional: bestes Paar automatisch in Keyframe A/B eintragen?
APPLY_BEST_PAIR = False

# Gewichtung der Teil-Scores für Gesamtrang
W_PARALLAX = 0.65   # Wichtigster Anteil
W_COVERAGE = 0.25   # Bildabdeckung (Fläche der Marker)
W_COUNT = 0.10      # Anzahl gemeinsamer Tracks

# ----------------------------- Hilfsfunktionen --------------------------------

def get_active_clip(context):
    """Aktiven MovieClip aus dem Movie Clip Editor holen (oder Fallback)."""
    space = getattr(context, "space_data", None)
    if space and getattr(space, "type", None) == "CLIP_EDITOR" and getattr(space, "clip", None):
        return space.clip
    # Fallback: erster Clip in der Datei
    return bpy.data.movieclips[0] if bpy.data.movieclips else None


def spread_area_norm(coords):
    """
    Grobe Bildabdeckung: Fläche der Bounding Box der Punkte (in [0..1]) relativ zur Bildfläche.
    Liefert 0..1.
    """
    if not coords:
        return 0.0
    xs = [c.x for c in coords]
    ys = [c.y for c in coords]
    bb_w = max(xs) - min(xs)
    bb_h = max(ys) - min(ys)
    area = max(0.0, bb_w) * max(0.0, bb_h)
    return float(area)


def parallax_score(pairs):
    """
    Parallax-Score: RMS der Residuen nach Abzug der mittleren Verschiebung.
    Reine Rotation/gleichförmige Verschiebung -> kleine Residuen; echte Parallaxe -> große Residuen.
    Erwartet Liste von (marker_a, marker_b).
    """
    if not pairs:
        return 0.0

    dvs = []
    for ma, mb in pairs:
        da = Vector((ma.co[0], ma.co[1]))
        db = Vector((mb.co[0], mb.co[1]))
        dvs.append(db - da)

    mean = Vector((0.0, 0.0))
    for d in dvs:
        mean += d
    mean /= len(dvs)

    sse = 0.0
    for d in dvs:
        res = d - mean
        sse += res.length_squared
    rms = math.sqrt(sse / len(dvs))
    return float(rms)


def format_row(r):
    return (f"A={r['fa']:>5}  B={r['fb']:>5}  "
            f"Score={r['total']:.4f}  Parallax={r['parallax']:.4f}  "
            f"Coverage={r['coverage']:.3f}  Tracks={r['count']:>3}")


def write_textblock(name, lines):
    """Ergebnis in einen Text-Block schreiben (für einfache Ablage)."""
    tb = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    tb.clear()
    for ln in lines:
        tb.write(ln + "\n")
    return tb


def apply_keyframes(clip, fa, fb):
    """Setzt Keyframe A/B in den Clip-Tracking-Settings."""
    settings = clip.tracking.settings
    settings.keyframe1 = fa
    settings.keyframe2 = fb


# ----------------------------- Neue schnelle Indizes --------------------------

def _build_marker_indices(tracks):
    """Erzeuge schnelle Nachschlagewerke:
    - track_index: track -> {frame: marker}
    - frame_tracks: frame -> set(tracks mit Marker in diesem Frame)
    """
    track_index = {}
    frame_tracks = defaultdict(set)
    for tr in tracks:
        if getattr(tr, "mute", False) or getattr(tr, "hide", False):
            continue
        fm = {}
        for m in getattr(tr, "markers", []):
            if getattr(m, "mute", False):
                continue
            f = int(getattr(m, "frame", -1))
            if f >= 0:
                fm[f] = m
                frame_tracks[f].add(tr)
        if fm:
            track_index[tr] = fm
    return track_index, frame_tracks


def _score_pair_fast(track_index, frame_tracks, fa, fb, min_common_tracks):
    """Bewertet ein Framepaar auf Basis der vorab gebauten Indizes.
    Liefert Dict (wie vorher) oder None, wenn unbrauchbar.
    """
    common_tracks = frame_tracks.get(fa, set()) & frame_tracks.get(fb, set())
    if len(common_tracks) < int(min_common_tracks):
        return None

    pairs = []
    for tr in common_tracks:
        mfa = track_index[tr].get(fa)
        mfb = track_index[tr].get(fb)
        if mfa and mfb:
            pairs.append((mfa, mfb))

    count = len(pairs)
    if count < int(min_common_tracks):
        return None

    pscore = parallax_score(pairs)

    coords_union = []
    for ma, mb in pairs:
        coords_union.append(Vector((ma.co[0], ma.co[1])))
        coords_union.append(Vector((mb.co[0], mb.co[1])))
    cscore = spread_area_norm(coords_union)

    count_score = min(1.0, count / 100.0)
    total = (W_PARALLAX * pscore) + (W_COVERAGE * cscore) + (W_COUNT * count_score)
    return {
        "fa": fa,
        "fb": fb,
        "total": total,
        "parallax": pscore,
        "coverage": cscore,
        "count": count,
    }


def scan_pairs(clip, frame_start, frame_end, step, tracks,
               *, min_gap, min_common_tracks,
               time_budget_s=None, max_pairs=None, progress_log_every=1000):
    """Alle brauchbaren Paare scannen – mit O(1)-Markerzugriff, früher Filterung und optionalem Zeit-/Mengengrenzer.
    Gibt (results, truncated_flag) zurück.
    """
    t0 = time.monotonic()
    results = []
    checked = 0
    truncated = False

    track_index, frame_tracks = _build_marker_indices(tracks)

    for fa in range(frame_start, frame_end + 1, int(step)):
        fb_min = fa + int(min_gap)
        if fb_min > frame_end:
            continue
        for fb in range(fb_min, frame_end + 1, int(step)):
            checked += 1

            # Limits prüfen
            if max_pairs is not None and checked > int(max_pairs):
                truncated = True
                break
            if time_budget_s is not None and (time.monotonic() - t0) > float(time_budget_s):
                truncated = True
                break

            s = _score_pair_fast(track_index, frame_tracks, fa, fb, min_common_tracks)
            if s:
                results.append(s)

            if progress_log_every and (checked % int(progress_log_every) == 0):
                print(f"[Parallax] scanned={checked} results={len(results)} fa={fa} fb={fb}")

        if truncated:
            break

    return results, truncated


# ----------------------------- Öffentliche API --------------------------------

def run_parallax_keyframe(context,
                          *,
                          apply_best_pair=False,
                          min_frame_gap=MIN_FRAME_GAP,
                          frame_step=FRAME_STEP,
                          min_common_tracks=MIN_COMMON_TRACKS,
                          top_k=TOP_K,
                          time_budget_s=2.0,        # NEU: Zeitbudget
                          max_pairs=40000,          # NEU: harte Obergrenze
                          progress_log_every=2000   # optionales Fortschritts-Logging
                          ):
    """
    Öffentliche API für den Coordinator. Liefert ein Ergebnis-Dict und
    kann optional das beste Paar in Keyframe A/B setzen.
    """
    _old = (MIN_FRAME_GAP, FRAME_STEP, MIN_COMMON_TRACKS, TOP_K)
    # temporär Parameter anwenden
    try:
        mg = int(min_frame_gap)
        st = int(frame_step)
        mc = int(min_common_tracks)
        tk = int(top_k)
    except Exception:
        mg, st, mc, tk = MIN_FRAME_GAP, FRAME_STEP, MIN_COMMON_TRACKS, TOP_K

    globals()["MIN_FRAME_GAP"] = mg
    globals()["FRAME_STEP"] = st
    globals()["MIN_COMMON_TRACKS"] = mc
    globals()["TOP_K"] = tk

    try:
        clip = get_active_clip(context)
        if not clip:
            return {"status": "NO_CLIP"}

        # defensiv: mute/hide je nach Build unterschiedlich
        tracks = [t for t in clip.tracking.tracks if not getattr(t, "mute", False) and not getattr(t, "hide", False)]
        if not tracks:
            return {"status": "NO_TRACKS"}

        frame_start = int(clip.frame_start)
        frame_end = int(clip.frame_start + clip.frame_duration - 1)

        results, truncated = scan_pairs(
            clip, frame_start, frame_end, FRAME_STEP, tracks,
            min_gap=MIN_FRAME_GAP,
            min_common_tracks=MIN_COMMON_TRACKS,
            time_budget_s=time_budget_s,
            max_pairs=max_pairs,
            progress_log_every=progress_log_every,
        )
        if not results:
            return {"status": "NO_PAIRS", "truncated": truncated}

        results.sort(key=lambda r: r["total"], reverse=True)
        top = results[:TOP_K]

        applied = False
        if apply_best_pair and top:
            best = top[0]
            apply_keyframes(clip, best["fa"], best["fb"])
            applied = True

        return {
            "status": "OK",
            "clip": clip.name,
            "top": top,
            "applied": applied,
            "truncated": truncated,
            "params": {
                "min_frame_gap": MIN_FRAME_GAP,
                "frame_step": FRAME_STEP,
                "min_common_tracks": MIN_COMMON_TRACKS,
                "top_k": TOP_K,
                "time_budget_s": time_budget_s,
                "max_pairs": max_pairs,
            }
        }
    finally:
        # Defaults zurücksetzen
        (globals()["MIN_FRAME_GAP"],
         globals()["FRAME_STEP"],
         globals()["MIN_COMMON_TRACKS"],
         globals()["TOP_K"]) = _old


# ----------------------------- Hauptausführung --------------------------------

def main(context):
    """Standalone-Lauf: Vorschläge erzeugen, Textblock schreiben, optional Keyframes setzen."""
    res = run_parallax_keyframe(
        context,
        apply_best_pair=APPLY_BEST_PAIR,
        min_frame_gap=MIN_FRAME_GAP,
        frame_step=FRAME_STEP,
        min_common_tracks=MIN_COMMON_TRACKS,
        top_k=TOP_K,
        time_budget_s=2.0,
        max_pairs=40000,
    )

    status = res.get("status")
    if status != "OK":
        print(f"[Parallax Helper] Abbruch: {status}")
        return

    clip_name = res.get("clip", "?")
    params = res.get("params", {})
    lines = [
        f"Parallax Keyframe Suggestions for '{clip_name}'",
        f"Step={params.get('frame_step', FRAME_STEP)}, "
        f"MinGap={params.get('min_frame_gap', MIN_FRAME_GAP)}, "
        f"MinCommonTracks={params.get('min_common_tracks', MIN_COMMON_TRACKS)}",
        "-" * 78,
    ]

    for i, r in enumerate(res["top"], 1):
        line = f"{i:>2}. {format_row(r)}"
        lines.append(line)
        print(line)

    write_textblock("parallax_keyframe_suggestions.txt", lines)

    if res.get("applied"):
        best = res["top"][0]
        print(f"[Parallax Helper] Bestes Paar gesetzt: A={best['fa']}  B={best['fb']}")
    if res.get("truncated"):
        print("[Parallax Helper] Hinweis: Scan wurde durch Zeit-/Mengengrenze gekappt (truncated=True).")
    print("[Parallax Helper] Fertig.")


# Direkt ausführen
if __name__ == "__main__":
    main(bpy.context)
