"""Utility to cycle through motion models."""

from typing import Iterator


def motion_model_cycle() -> Iterator[str]:
    models = [
        'Perspective',
        'Affine',
        'LocRotScale',
        'LocRot',
        'Loc'
    ]
    idx = 0
    while True:
        yield models[idx % len(models)]
        idx += 1
