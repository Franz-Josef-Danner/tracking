# Kaiserlich Track Addon

This repository contains a simple Blender addon. **Important:** zip the files directly so that `__init__.py` sits at the archive root; Blender extracts the archive into a folder with that name and expects the module at the top level. The addon adds a panel to the Movie Clip Editor for custom tracking options.

## Installation
1. In Blender open **Edit > Preferences > Add-ons**.
2. Click **Install...** and pick the zip archive that contains the addon files
   (with `__init__.py` directly in the zip root).
3. Enable the addon from the list under the *Movie Clip* category.

## Usage
1. Open the Movie Clip Editor and switch to **Tracking** context.
2. Press **N** to reveal the sidebar and choose the **Kaiserlich** tab.
3. Adjust the properties and click **Start** to run the operator.
4. Existing proxies are removed, then a 50% proxy and a timecode
   index are built. The addon waits up to 300&nbsp;s for a proxy
   file to appear, printing a countdown in the console. After that it
   disables the proxy timeline, detects features and filters them
   automatically. When a callback is registered, additional actions
   such as bidirectional tracking can run afterward without a separate
   button.

The main operator now relies on `detect_until_count_matches`. This helper
repeatedly runs feature detection and adapts the settings until the number of
markers falls within the expected range. Once a satisfactory count is achieved,
all newly created tracks are renamed with the ``TRACK_`` prefix.
If the same low-marker frame is found repeatedly, the addon cycles through
different motion models and adjusts the ``min_marker_count_plus`` value.
After the frame appears ten times in a row the operator stops with a warning.

### Callbacks

Custom scripts can run after the iterative detection finishes. **This
registration must be done every time the addon is loaded** so the callback can
run additional steps such as bidirectional tracking. Register a function with
``register_after_detect_callback`` before starting the operator:

```python
import tracking
import track_cycle

tracking.register_after_detect_callback(track_cycle.run)
```

The callback receives the current ``context`` object. The example in
``track_cycle.py`` enables proxy/timecode again using the toggle operator.
It then launches ``auto_track_bidir`` to track all ``TRACK_`` markers and
finally removes short ones with ``delete_short_tracks_with_prefix``.
Remaining tracks are renamed with the ``GOOD_`` prefix.

### Properties

The panel exposes several options:

- **min marker pro frame** – minimum marker count per frame (default 10)
- **min tracking length** – minimum length for each track (default 20)
- **Error Threshold** – maximum error allowed for trackers (default 0.04)

### Helper Scripts

Several utility modules are included for experimentation:

- `few_marker_frame.py` – locate frames with few markers and position the playhead.
- `marker_count_plus.py` – compute additional marker thresholds.
- `margin_utils.py` – derive margin and distance values and scale them relative to the detection threshold.
- `proxy_wait.py` – create proxies and timecode indices, show the proxy folder and a countdown until a file appears.
- `remove_existing_proxies` – helper inside `proxy_wait.py` to delete old proxy files before new ones are generated.
- `update_min_marker_props.py` – sync derived marker properties.
- `proxy_switch.py` – disable proxies after generation.
- `detect.py` – adaptive feature detection script that relies on `margin_utils.py` for margin and distance values.
- `distance_remove.py` – filter NEW_ markers near GOOD_ markers.
- `delete_new_markers` – remove all NEW_ markers from the active clip via the NEW_-Cleanup panel.
- `count_new_markers.py` – helper to count NEW_ markers on a clip.
- `iterative_detect.py` – repeatedly detect markers until the count fits and
  rename them with the prefix `TRACK_`.
- `auto_track_bidir.py` – operator to track markers named with the `TRACK_` prefix both backward and forward.
- `track_length.py` – delete `TRACK_` markers shorter than 25 frames and rename the remaining ones with `GOOD_`.
- `motion_model.py` – helpers to cycle or reset the default motion model.

## Running Tests

The tests run entirely outside Blender. You only need Python 3.8+ and the
`pytest` package (optional) to execute them. Dummy replacements for `bpy` and
`mathutils` are created automatically so no Blender installation is required.

Run all tests with:

```bash
pytest
```

or using the built-in unittest runner:

```bash
python -m unittest
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
