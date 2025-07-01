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

The add-on registers the following operators in the Movie Clip Editor and
prints diagnostic information in the console:

- **Detect Features (Custom)** – detects tracking features with predefined
  settings.
- **Auto Track Selected** – tracks all selected markers forward.
- **Start Tracking Cycle** – iteratively searches for frames with few
  markers, detects new features and tracks them forward.

Both the minimum number of markers per frame and the minimum number of
features to detect can be configured in the panel before running the
operators.

