# Tracking Add-on

This repository contains simple Blender scripts to automate movie clip
tracking. The main script `combined_cycle.py` combines feature detection,
auto tracking and playhead search in a repeating cycle. It can be run from
the Blender text editor or installed as an add-on.
All other scripts in this repository are prototypes of the individual steps
now bundled in `combined_cycle.py`.

## Installation
1. Open Blender and switch to the *Scripting* workspace.
2. Load `combined_cycle.py` in the text editor and press **Run Script**, or
   install the folder as an add-on via *Edit → Preferences → Add-ons →
   Install...*.

When installed as an add-on, a single panel named **Tracking Cycle** appears in
the Movie Clip Editor. It provides only the minimum marker count input, a
progress label showing the current frame out of the total, and a button to start
the cycle. Heavy operations like feature detection and auto tracking run
synchronously and may temporarily block Blender's UI, so the status text helps
indicate progress. The currently processed frame is also printed to the console
for quick feedback. A boolean option **Cleanup Verbose** controls whether the
distance from each `NEU_` marker to `GOOD_` markers is printed during cleanup.

The following operators are registered for internal use and can also be called
via Blender's operator search:

- **Start Tracking Cycle** – iteratively searches for frames with few markers,
  detects new features and tracks them forward.
- **Auto Track Selected** – selects all tracks named `TRACK_*` and tracks them forward.
- **Delete Short Tracks with Prefix** – removes all tracking tracks starting
  with `TRACK_` that are shorter than the "Min Track Length" property and
  renames the remaining ones to `GOOD_`.
- **Clear RAM Cache** – reloads the current clip to free memory.
- **Cleanup Excess Markers** – scans each frame for excessive markers and
  repeatedly deletes the worst ones until every frame meets the minimum count.

The minimum marker count used for the playhead search is configured in the
panel before running the operator. Feature detection now aims to create a
number of new tracks between *Min Marker Count × 4 × 0.8* and
*Min Marker Count × 4 × 1.2*. If too few or too many markers are found, the
detection threshold is adjusted with
``threshold *= (new_count + 0.1) / (Min Marker Count × 4)``
and detection is attempted again until the
result falls inside this range. The search margin and minimum distance scale
with ``log10(threshold * 100000) / 5`` so wider thresholds consider a broader area.
The threshold is clamped to a minimum of ``0.0001`` so it never becomes too small.
Newly created markers receive the prefix `NEU_` during each attempt. If the
detected count falls in the expected range they are renamed to `TRACK_`; if not
they are deleted and detection runs again.
After tracking forward and removing tracks that are too short, the remaining
`TRACK_` markers are renamed to `GOOD_` so they are skipped in subsequent
iterations.
During the tracking cycle the RAM cache is cleared automatically before jumping
to the next frame. Once the end frame is reached the playhead returns to the
scene start and the cycle runs a second time. All detection values are reset to
their defaults before this second pass begins.
Each visited frame is remembered. If the playhead revisits one of these frames
the value of **Marker Count Plus** increases by 10, widening the expected
range for new markers. Landing on a new frame decreases the value by 10 again,
but never below its original starting value. The "Marker Count Plus" value
is clamped to ``Min Marker Count × 200``.

If the playhead lands on the same frame as in the previous tracking step, the
default pattern size for newly detected features grows by **10 %**. The motion
model cycles to the next type (Loc → LocRot → LocScale → LocRotScale → Affine →
Perspective). Reaching a new frame decreases the pattern size by the same
percentage and resets the motion model back to **Loc**. The search size always
updates to twice the current pattern size. Pattern sizes are capped at 150,
allowing difficult frames to be tracked with progressively larger or smaller
areas without exceeding this limit.

If the search finds the same frame twenty times in a row, the playhead jumps back to the scene start. All detection values reset to their defaults and the cycle continues from the beginning. Each repeated attempt prints
``[Cycle] Repeat attempt n/20 on frame x`` to the console so it's easy to see how close the loop is to restarting.

## Standalone Cleanup Script

`distance_remove.py` is a small helper that can be run directly from
Blender's text editor. When executed it registers the **Cleanup NEU_ Markers**
operator, which deletes `NEU_` markers that are closer than a user-defined
distance to existing `GOOD_` markers in the current frame. Running the script
again automatically unregisters the previous instance so it can be tested
multiple times without restarting Blender.

## Function Test Scripts

In addition to `combined_cycle.py` the repository includes several standalone
scripts that were used to verify each step of the workflow. They remain
executable from Blender's text editor, although their functionality is now
incorporated into the main cycle:

- `Track Length.py` – removes tracks named `TRACK_` that are shorter than 25 frames.
- `detect.py` – panel for repeatedly detecting features until a minimum count is reached.
- `playhead.py` – finds the first frame with too few markers and sets the playhead.
- `catch clean.py` – reloads the clip to clear its RAM cache.
- `Proxy switch.py` – header button to toggle proxy usage. The operator waits
  two seconds after switching so the UI can refresh.
- `proxy rechner.py` – estimates memory usage and suggests a proxy size.
- `proxy wait.py` – creates a 50 % proxy and waits for its files to appear.
- `distance_remove.py` – operator that deletes `NEU_` markers too close to `GOOD_` markers.
- `track.py` – operator to track selected markers forward.
- `track_marker_size_adapt.py` – tracks one frame at a time until markers stop moving.
- `margin a Distanz.py` – calculates detection margin and distance from clip width.
- `min marker rechner.py` – helper for computing the marker count range used by detection.

These scripts can be executed from Blender's text editor for experimentation,
but the full workflow resides in `combined_cycle.py`.
This project is released under the MIT License. See the `LICENSE` file for
details.

