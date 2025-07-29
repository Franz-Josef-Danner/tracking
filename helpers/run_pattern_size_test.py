from ._run_test_cycle import _run_test_cycle


def run_pattern_size_test(context):
    """Execute a single cycle for the current pattern size with one tracking pass."""
    return _run_test_cycle(context, cleanup=True, cycles=1)
