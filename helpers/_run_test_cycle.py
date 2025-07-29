from .run_iteration import run_iteration
from .delete_tracks import delete_selected_tracks


def _run_test_cycle(context, cleanup=False, cycles=4):
    """Run detection and tracking multiple times and return total frames and error."""
    clip = context.space_data.clip
    total_end = 0
    total_error = 0.0
    for i in range(cycles):
        print(f"[Test Cycle] Durchgang {i + 1}")
        frames, err = run_iteration(context)
        total_end += frames
        total_error += err
    if cleanup:
        for t in clip.tracking.tracks:
            t.select = True
        delete_selected_tracks()
    print(f"[Test Cycle] Summe End-Frames: {total_end}, Error: {total_error:.4f}")
    return total_end, total_error
