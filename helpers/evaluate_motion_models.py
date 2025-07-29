from ._run_test_cycle import _run_test_cycle


def evaluate_motion_models(context, models=None, cycles=2):
    """Return the best motion model along with its score and error."""
    if models is None:
        models = ['Loc', 'LocRot', 'LocScale', 'LocRotScale', 'Affine', 'Perspective']
    clip = context.space_data.clip
    settings = clip.tracking.settings
    best_model = settings.default_motion_model
    best_score = None
    best_error = None
    for model in models:
        settings.default_motion_model = model
        score, err = _run_test_cycle(context, cycles=cycles)
        print(f"[Test Motion] model={model} frames={score} error={err:.4f}")
        if best_score is None or score > best_score or (
            score == best_score and (best_error is None or err < best_error)
        ):
            best_score = score
            best_error = err
            best_model = model
    settings.default_motion_model = best_model
    return best_model, best_score, best_error
