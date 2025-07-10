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
4. Existing proxies are removed, the addon waits for proxy generation,
   disables proxies, then runs marker detection and cleanup
   automatically.

### Properties

The panel exposes several options:

- **min marker pro frame** – minimum marker count per frame (default 10)
- **min tracking length** – minimum length for each track (default 20)
- **Error Threshold** – maximum error allowed for trackers (default 0.04)
- **Proxy Wait** – optional wait time passed to the proxy helper when
  available. Proxy creation is performed as the final step of the
  operation and defaults to 300 s.

### Helper Scripts

Several utility modules are included for experimentation:

- `find_frame_with_few_tracking_markers.py` – locate frames with few markers.
- `get_marker_count_plus.py` – compute additional marker thresholds.
- `margin_a_distanz.py` – derive margin and distance values from the clip width.
- `playhead.py` – utilities for repositioning the playhead.
- `proxy_wait.py` – create proxies and wait for completion.
- `remove_existing_proxies` – helper inside `proxy_wait.py` to delete old
  proxy files before new ones are generated.
- `update_min_marker_props.py` – sync derived marker properties.
- `proxy_switch.py` – disable proxies after generation.
- `detect.py` – adaptive feature detection script.
- `distance_remove.py` – filter NEU_ markers near GOOD_ markers.
