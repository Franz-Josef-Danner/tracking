# Kaiserlich Track Addon

This repository contains a simple Blender addon. **Important:** the
`__init__.py` file must reside at the root of the addon alongside all helper
modules. When zipping the addon, select all files directly and **do not**
include an extra parent folder. Blender extracts the archive into a new
directory whose name matches the zip file, so the root must contain
`__init__.py`. The addon adds a panel to the Movie Clip Editor for custom
tracking options.
If the addon is nested in another directory when the zip is created,
Blender will fail to load the module. Double-check that `__init__.py` and
the helper scripts sit directly in the archive root before installing.

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
   automatically.

### Properties

The panel exposes several options:

- **min marker pro frame** – minimum marker count per frame (default 10)
- **min tracking length** – minimum length for each track (default 20)
- **Error Threshold** – maximum error allowed for trackers (default 0.04)

### Helper Scripts

Several utility modules are included for experimentation:

- `few_marker_frame.py` – locate frames with few markers.
- `marker_count_plus.py` – compute additional marker thresholds.
- `margin_a_distanz.py` – derive margin and distance values from the clip width.
- `margin_distance_adapt.py` – ensure margin and distance are stored on the clip and scaled relative to the detection threshold.
- `playhead.py` – utilities for repositioning the playhead.
- `proxy_wait.py` – create proxies and timecode indices, show the proxy folder and a countdown until a file appears.
- `remove_existing_proxies` – helper inside `proxy_wait.py` to delete old proxy files before new ones are generated.
- `update_min_marker_props.py` – sync derived marker properties.
- `proxy_switch.py` – disable proxies after generation.
- `detect.py` – adaptive feature detection script that uses margin and distance values from `margin_a_distanz.py`.
- `distance_remove.py` – filter NEW_ markers near GOOD_ markers.
- `count_new_markers.py` – helper to count NEW_ markers on a clip.
- `iterative_detect.py` – repeatedly detect markers until the count fits and
  rename them with the prefix `TRACK_`.
