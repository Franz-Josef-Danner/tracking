import bpy


def detect_features(context, values):
    space = context.space_data
    clip = space.clip
    settings = clip.tracking.settings

    # Pattern & Search Größen (müssen ints sein)
    settings.default_pattern_size = max(5, int(values['pz']))
    settings.default_search_size = max(settings.default_pattern_size + 2, int(values['sz']))

    # Clamp min_distance hart zur Sicherheit
    md = max(2, min(int(values['md']), 2048))
    if md != values['md']:
        values['md'] = md  # sync

    print(f"[Kaiserlich][detect] threshold={values['tr']} margin={values['ma']} md={values['md']}")
    bpy.ops.clip.detect_features(
        placement='FRAME',
        margin=int(values['ma']),
        threshold=values['tr'],
        min_distance=md
    )
