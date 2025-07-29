import re
from .utils import PENDING_RENAME
from .clean_pending_tracks import clean_pending_tracks


def rename_pending_tracks(clip):
    """Rename pending tracks sequentially and clear the list."""
    clean_pending_tracks(clip)
    if not PENDING_RENAME:
        return
    existing_numbers = []
    for t in clip.tracking.tracks:
        try:
            m = re.search(r"(\d+)$", t.name)
            if m:
                existing_numbers.append(int(m.group(1)))
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Lesen des Marker-Namens: {t} ({e})")
    next_num = max(existing_numbers) + 1 if existing_numbers else 1
    for t in PENDING_RENAME:
        try:
            _ = t.name
        except Exception as e:
            print(f"\u26a0\ufe0f Fehler beim Marker-Name: {t} ({e})")
            t.name = f"Track {next_num:03d}"
        else:
            t.name = f"Track {next_num:03d}"
        next_num += 1
    PENDING_RENAME.clear()
