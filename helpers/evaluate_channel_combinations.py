from ._run_test_cycle import _run_test_cycle


def evaluate_channel_combinations(context, combos=None, cycles=2):
    """Return the best RGB channel combination with its score and error."""
    if combos is None:
        combos = [
            (True, False, False),
            (True, True, False),
            (True, True, True),
            (False, True, False),
            (False, True, True),
            (False, False, True),
        ]
    clip = context.space_data.clip
    settings = clip.tracking.settings
    best_combo = (
        settings.use_default_red_channel,
        settings.use_default_green_channel,
        settings.use_default_blue_channel,
    )
    best_score = None
    best_error = None
    for combo in combos:
        r, g, b = combo
        settings.use_default_red_channel = r
        settings.use_default_green_channel = g
        settings.use_default_blue_channel = b
        score, err = _run_test_cycle(context, cycles=cycles)
        print(f"[Test Channel] combo={combo} frames={score} error={err:.4f}")
        if best_score is None or score > best_score or (
            score == best_score and (best_error is None or err < best_error)
        ):
            best_score = score
            best_error = err
            best_combo = combo
    (
        settings.use_default_red_channel,
        settings.use_default_green_channel,
        settings.use_default_blue_channel,
    ) = best_combo
    return best_combo, best_score, best_error
