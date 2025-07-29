from .utils import TIMER_INTERVAL


def add_timer(window_manager, window):
    """Create a timer using the global `TIMER_INTERVAL`."""
    return window_manager.event_timer_add(TIMER_INTERVAL, window=window)
