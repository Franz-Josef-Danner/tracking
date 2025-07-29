import bpy
from .evaluate_tracking import evaluate_tracking  # ensure this function is available


def set_color_channels(channels=("R", "G", "B")):
    """Activate or deactivate RGB channels in tracking settings."""
    settings = bpy.context.space_data.clip.tracking.settings
    settings.use_red_channel = 'R' in channels
    settings.use_green_channel = 'G' in channels
    settings.use_blue_channel = 'B' in channels


def optimize_tracking_parameters():
    """Try different motion models and color channel combos, selecting the best."""
    tracking_settings = bpy.context.space_data.clip.tracking.settings

    # Test motion models
    motion_models = ['Loc', 'LocRot', 'Affine', 'Perspective']
    best_score = float('-inf')
    best_model = tracking_settings.motion_model

    for model in motion_models:
        tracking_settings.motion_model = model
        length, error, score = evaluate_tracking()
        if score > best_score:
            best_score = score
            best_model = model

    tracking_settings.motion_model = best_model

    # Test color channel combinations
    channel_combinations = [
        ('R',), ('G',), ('B',),
        ('R', 'G'), ('G', 'B'), ('R', 'B'),
        ('R', 'G', 'B')
    ]

    best_score = float('-inf')
    best_combo = ('R', 'G', 'B')

    for combo in channel_combinations:
        set_color_channels(combo)
        length, error, score = evaluate_tracking()
        if score > best_score:
            best_score = score
            best_combo = combo

    set_color_channels(best_combo)
