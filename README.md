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

### Helper Scripts

Several utility modules are included for experimentation:

- `find_frame_with_few_tracking_markers.py` – locate frames with few markers.
- `get_marker_count_plus.py` – compute additional marker thresholds.
- `margin_a_distanz.py` – derive margin and distance values from the clip width.
- `playhead.py` – utilities for repositioning the playhead.
- `proxy_wait.py` – create proxies and wait for completion.
- `update_min_marker_props.py` – sync derived marker properties.
