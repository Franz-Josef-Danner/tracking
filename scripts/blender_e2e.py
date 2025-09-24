"""
Headless Blender E2E runner for the tracking addon.

Usage (run outside Blender):
  blender --background --python scripts/blender_e2e.py -- --clip /path/to/clip.mp4 --out /tmp/out.json

Notes:
- The script attempts to make the repository importable inside Blender by adding its parent directory to sys.path.
- It loads the movieclip into `bpy.data.movieclips` and passes it to `Operator.orchestrator.run_autotrack`.
- The script does NOT install the addon in Blender; ensure the addon files are reachable by `sys.path` or installed.
"""

import sys
import os
import argparse
import json

# Blender imports are local to runtime; wrap in try/except for helpful errors
try:
    import bpy
except Exception as e:
    print("This script must be run inside Blender (python bundled with Blender). Error:", e)
    raise

# parse args after Blender's own args
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

parser = argparse.ArgumentParser(description="Run run_autotrack headless")
parser.add_argument("--clip", required=True, help="Path to movie clip (mp4/mov)")
parser.add_argument("--out", required=False, default="/tmp/tracking_e2e_result.json", help="Output JSON file")
parser.add_argument("--repo-root", required=False, default=None, help="Optional path to repository root to add to sys.path")
args = parser.parse_args(argv)

clip_path = os.path.abspath(args.clip)
out_path = os.path.abspath(args.out)

# If provided, add repo root to sys.path; otherwise attempt to find project root relative to this script
if args.repo_root:
    repo_root = os.path.abspath(args.repo_root)
else:
    # assume this script lives in <repo>/scripts/
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

print(f"Using repo root: {repo_root}")
print(f"Loading clip: {clip_path}")

result = {"ok": False, "error": None}
try:
    # Ensure the movieclip is loaded (Blender caches duplicates automatically)
    clip = None
    try:
        clip = bpy.data.movieclips.load(clip_path)
    except Exception as e:
        # If already loaded, try to reuse
        for mc in bpy.data.movieclips:
            if getattr(mc, "filepath", "") == clip_path or os.path.basename(getattr(mc, "filepath", "")) == os.path.basename(clip_path):
                clip = mc
                break
        if clip is None:
            raise

    # Import orchestrator
    try:
        from Operator.orchestrator import run_autotrack
    except Exception:
        # try package import if script is run from a different CWD
        import importlib
        orchestrator = importlib.import_module("Operator.orchestrator")
        run_autotrack = getattr(orchestrator, "run_autotrack")

    # Run (use current context)
    print("Starting run_autotrack...")
    res = run_autotrack(bpy.context, clip)
    result["ok"] = True
    result["result"] = res
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    print("Error during run:", e)
    print(tb)
    result["error"] = str(e)
    result["traceback"] = tb

# Write JSON output
try:
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote result to {out_path}")
except Exception as e:
    print("Failed to write output:", e)

# Exit Blender gracefully
print("Done.")
