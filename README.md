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

When installed as an add-on, a panel named **Tracking Cycle** appears in the
Movie Clip Editor. It shows the current status string as well as the processed
frame number out of the total scene range. Heavy operations like feature
detection or auto tracking run synchronously and may block the UI momentarily,
so the status text helps indicate progress.

The add-on registers the following operators in the Movie Clip Editor and
prints diagnostic information in the console:

- **Start Tracking Cycle** – iteratively searches for frames with few
  markers, detects new features and tracks them forward.
- **Delete Short Tracks with Prefix** – removes all tracking tracks starting
  with `TRACK_` that are shorter than 25 frames.
- **Clear RAM Cache** – reloads the current clip to free memory.

The minimum marker count used for detection and frame search can be configured
in the panel before running the operator. During the tracking cycle the
RAM cache is cleared automatically before jumping to the next frame.

This project is released under the MIT License. See the `LICENSE` file for
details.

