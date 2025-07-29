from .utils import PENDING_RENAME


def add_pending_tracks(tracks):
    """Store new tracks for later renaming with validation."""
    for t in tracks:
        try:
            if (
                isinstance(t.name, str)
                and t.name.strip()
                and t not in PENDING_RENAME
            ):
                PENDING_RENAME.append(t)
        except Exception:
            print(f"\u26a0\ufe0f Ungültiger Marker übersprungen: {t}")
