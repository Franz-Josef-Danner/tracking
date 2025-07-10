# Kaiserlich Track Addon

This repository contains a simple Blender addon. **Important:** the
`__init__.py` file must reside at the root of the addon and not inside a
subfolder. The helper modules live inside the `kaiserlich_track`
directory. When creating a zip for installation, ensure `__init__.py`
is directly in the zip and the `kaiserlich_track` folder is alongside
it. The addon adds a panel to the Movie Clip Editor for custom tracking
options.

## Installation
1. In Blender open **Edit > Preferences > Add-ons**.
2. Click **Install...** and pick the zip archive that contains
   `__init__.py` in its root next to the `kaiserlich_track` folder.
3. Enable the addon from the list under the *Movie Clip* category.

## Usage
1. Open the Movie Clip Editor and switch to **Tracking** context.
2. Press **N** to reveal the sidebar and choose the **Kaiserlich** tab.
3. Adjust the properties and click **Start** to run the operator.

### Helper Scripts

Several utility modules are included for experimentation:

- `find_frame_with_few_tracking_markers.py` – locate frames with few markers.
- `get_marker_count_plus.py` – compute additional marker thresholds.
- `margin_a_distanz.py` – derive margin and distance values from the clip width.
- `playhead.py` – utilities for repositioning the playhead.
- `proxy_wait.py` – create proxies and wait for completion.
- `update_min_marker_props.py` – sync derived marker properties.

