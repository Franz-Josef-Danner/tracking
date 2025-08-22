from future import annotations

import bpy



# Utility-Funktionen für Marker-Namen und Pattern-Triplet



from typing import Iterable, List, Set, Tuple

def _collect_track_pointers(tracks: Iterable[bpy.types.MovieTrackingTrack]) -> Set[int]: return {t.as_pointer() for t in tracks}

def _collect_new_track_names_by_pointer( tracks: Iterable[bpy.types.MovieTrackingTrack], before_ptrs: Set[int] ) -> List[str]: return [t.name for t in tracks if t.as_pointer() not in before_ptrs]

def _select_tracks_by_names(tracking: bpy.types.MovieTracking, names: Set[str]) -> int: count = 0 for t in tracking.tracks: sel = t.name in names t.select = sel if sel: count += 1 return count

def _set_pattern_size(tracking: bpy.types.MovieTracking, new_size: int) -> int: s = tracking.settings clamped = max(3, min(101, int(new_size))) try: s.default_pattern_size = clamped except Exception: pass return int(getattr(s, "default_pattern_size", clamped))

def _get_pattern_size(tracking: bpy.types.MovieTracking) -> int: try: return int(tracking.settings.default_pattern_size) except Exception: return 15

def _run_detect_features_in_context(margin: int = None, min_distance: int = None, threshold: float = None): kw = {} if margin is not None: kw["margin"] = int(margin) if min_distance is not None: kw["min_distance"] = int(min_distance) if threshold is not None: kw["threshold"] = float(threshold) try: return bpy.ops.clip.detect_features(**kw) except TypeError: return bpy.ops.clip.detect_features()



# Öffentliche Funktion: Pattern-Triplet mit Namensaggregation


def run_pattern_triplet_and_select_by_name( context: bpy.types.Context, *, scale_low: float = 0.8, scale_high: float = 1.2, also_include_ready_selection: bool = True, adjust_search_with_pattern: bool = False, ) -> dict: clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None) if not clip: for c in bpy.data.movieclips: clip = c break if not clip: print("[PatternTriplet] Kein MovieClip verfügbar.") return {"status": "FAILED", "reason": "no_movieclip"}

tracking = clip.tracking
settings = tracking.settings

pattern_o = _get_pattern_size(tracking)
search_o = int(getattr(settings, "default_search_size", 51))

aggregated_names: Set[str] = set()

if also_include_ready_selection:
    ready_names = [t.name for t in tracking.tracks if getattr(t, "select", False)]
    aggregated_names.update(ready_names)

def sweep_with_scale(scale: float) -> int:
    nonlocal tracking, settings, pattern_o, search_o, aggregated_names
    before_ptrs = _collect_track_pointers(tracking.tracks)

    new_pattern = max(3, int(round(pattern_o * float(scale))))
    _set_pattern_size(tracking, new_pattern)
    if adjust_search_with_pattern:
        try:
            settings.default_search_size = max(5, int(round(search_o * float(scale))))
        except Exception:
            pass

    try:
        bpy.ops.clip.detect_features('INVOKE_DEFAULT')
    except TypeError:
        bpy.ops.clip.detect_features()
    except Exception as ex:
        print(f"[PatternTriplet] detect_features Exception @scale={scale}: {ex}")

    try:
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    except Exception:
        pass

    new_names = _collect_new_track_names_by_pointer(tracking.tracks, before_ptrs)
    aggregated_names.update(new_names)
    return len(new_names)

created_low = sweep_with_scale(scale_low)
created_high = sweep_with_scale(scale_high)

_set_pattern_size(tracking, pattern_o)
try:
    settings.default_search_size = search_o
except Exception:
    pass

for t in tracking.tracks:
    t.select = False
selected = _select_tracks_by_names(tracking, aggregated_names)

try:
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
except Exception:
    pass

print(
    f"[PatternTriplet] DONE | pattern_o={pattern_o} | low={scale_low} -> +{created_low} | "
    f"high={scale_high} -> +{created_high} | selected_by_name={selected}"
)

return {
    "status": "READY",
    "created_low": int(created_low),
    "created_high": int(created_high),
    "selected": int(selected),
    "names": sorted(aggregated_names),
}



# Integration in run_detect_once (READY-Zweig)



from typing import Any, Dict, Optional

def run_detect_once( context: bpy.types.Context, *, start_frame: Optional[int] = None, threshold: Optional[float] = None, marker_adapt: Optional[int] = None, min_marker: Optional[int] = None, max_marker: Optional[int] = None, margin_base: Optional[int] = None, min_distance_base: Optional[int] = None, close_dist_rel: float = 0.01, handoff_to_pipeline: bool = False, post_pattern_triplet: bool = False,  # <<< NEU ) -> Dict[str, Any]: """ Beispielhafte vereinfachte run_detect_once-Integration mit Pattern-Triplet. (Hier nur der READY-Zweig erweitert; die volle Funktion aus deinem bestehenden Code müsste hier ersetzt oder entsprechend angepasst werden.) """ scn = context.scene clip = getattr(context, "edit_movieclip", None) or getattr(getattr(context, "space_data", None), "clip", None) if not clip: return {"status": "FAILED", "reason": "no_movieclip"}

tracking = clip.tracking
frame = int(scn.frame_current)

# <<< Stelle dir hier die gesamte Detect-Logik aus deiner bisherigen run_detect_once vor
# und springe in den READY-Zweig, wenn corridor passt.

# ...

# Beispiel READY-Zweig
result: Dict[str, Any] = {
    "status": "READY",
    "new_tracks": 10,
    "threshold": float(threshold or 0.75),
    "frame": int(frame),
}

if post_pattern_triplet:
    trip = run_pattern_triplet_and_select_by_name(context)
    result["pattern_triplet"] = trip

return result

