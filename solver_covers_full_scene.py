"""Utility: check if reconstruction covers entire frame range."""


def solver_covers_full_scene(clip):
    """Return ``True`` if the reconstruction includes all frames."""

    recon = clip.tracking.reconstruction
    if not recon.is_valid:
        return False

    frame_start = int(clip.frame_start)
    frame_end = int(clip.frame_start + clip.frame_duration - 1)
    frames = {cam.frame for cam in recon.cameras}
    if not frames:
        return False

    return (
        min(frames) <= frame_start
        and max(frames) >= frame_end
        and len(frames) >= (frame_end - frame_start + 1)
    )

