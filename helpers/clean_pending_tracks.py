from .utils import PENDING_RENAME


def clean_pending_tracks(clip):
    """Remove deleted tracks from the pending list."""
    names = set()
    for t in clip.tracking.tracks:
        try:
            if isinstance(t.name, str) and t.name.strip():
                names.add(t.name)
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Zugriff auf Marker-Name: {t} ({e})")
    remaining = []
    for t in PENDING_RENAME:
        try:
            if t.name in names:
                remaining.append(t)
        except UnicodeDecodeError:
            print(
                f"\u26a0\ufe0f Warnung: Marker-Name kann nicht gelesen werden (wahrscheinlich defekt): {t}"
            )
            continue
    PENDING_RENAME.clear()
    PENDING_RENAME.extend(remaining)
