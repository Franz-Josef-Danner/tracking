# detect.py
import unicodedata

def _safe_str(x):
    if isinstance(x, (bytes, bytearray)):
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                x = x.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            x = x.decode("latin-1", errors="replace")
    s = str(x).replace("\u00A0", " ")  # NBSP → Space
    return unicodedata.normalize("NFKC", s).strip()

def _sanitize_track_names(context):
    mc = getattr(context, "edit_movieclip", None) or getattr(context.space_data, "clip", None)
    if not mc: return
    for tr in getattr(mc.tracking, "tracks", []):
        try:
            tr.name = _safe_str(tr.name)
        except Exception:
            pass

def run_detect_once(context, start_frame: int, handoff_to_pipeline=True):
    # 1) Vorbereitend ALLES sanitisieren
    _sanitize_track_names(context)

    try:
        # … deine bisherige Detect-Logik …
        # Beispiele:
        # names = [_safe_str(t.name) for t in prev_raw_tracks]
        # open(file, encoding="utf-8") → bei Fehler retry mit encoding="latin-1"
        return {"status": "READY", "frame": start_frame}
    except UnicodeDecodeError as ex:
        # Einmaliger Retry nach zusätzlicher Sanitize
        _sanitize_track_names(context)
        try:
            # hier erneut Detect versuchen:
            # ...
            return {"status": "READY", "frame": start_frame}
        except Exception as ex2:
            return {"status": "FAILED", "reason": f"encoding:{ex2}"}
