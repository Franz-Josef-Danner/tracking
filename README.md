# Tracking Add-on

This repository contains simple Blender scripts to automate movie clip
tracking. The main script `combined_cycle.py` combines feature detection,
auto tracking and playhead search in a repeating cycle. It can be run from
the Blender text editor or installed as an add-on.

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
indicate progress.

The following operators are registered for internal use and can also be called
via Blender's operator search:

- **Start Tracking Cycle** – iteratively searches for frames with few markers,
  detects new features and tracks them forward.
- **Auto Track Selected** – selects all tracks named `TRACK_*` and tracks them forward.
- **Delete Short Tracks with Prefix** – removes all tracking tracks starting
  with `TRACK_` that are shorter than the "Min Track Length" property and
  renames the remaining ones to `GOOD_`.
- **Clear RAM Cache** – reloads the current clip to free memory.

The minimum marker count used for the playhead search is configured in the
panel before running the operator. Feature detection now aims to create a
number of new tracks between *Min Marker Count × 4 × 0.8* and
*Min Marker Count × 4 × 1.2*. If too few or too many markers are found, the
detection threshold is adjusted with
``threshold *= (new_count + 0.1) / (Min Marker Count × 4)``
and detection is attempted again until the
result falls inside this range. The search margin and minimum distance scale
with ``log10(threshold * 100000) / 5`` so wider thresholds consider a broader area.
Newly created markers receive the prefix `NEU_` during each attempt. If the
detected count falls in the expected range they are renamed to `TRACK_`; if not
they are deleted and detection runs again.
After tracking forward and removing tracks that are too short, the remaining
`TRACK_` markers are renamed to `GOOD_` so they are skipped in subsequent
iterations.
During the tracking cycle the RAM cache is cleared automatically before jumping
to the next frame. When tracking hits the scene end, the proxy is rebuilt and
the cycle restarts from the beginning.
Each visited frame is remembered. If the playhead revisits one of these frames
the value of **Marker Count Plus** increases by 10, widening the expected
range for new markers. Landing on a new frame decreases the value by 10 again,
but never below its original starting value.

This project is released under the MIT License. See the `LICENSE` file for
details.

