 # Blender headless E2E runner

 This folder contains `blender_e2e.py`, a small helper to run the addon's `run_autotrack` function in Blender headless mode.

 Usage (from terminal where `blender` is on PATH):

 ```bash
 blender --background --python scripts/blender_e2e.py -- --clip /path/to/clip.mp4 --out /tmp/out.json --repo-root /path/to/tracking
 ```

 Notes:

 - `--repo-root` (optional) helps Blender find the local repository if the addon isn't installed.
 - The script expects Blender's `bpy` to be available (run inside Blender).
 - The resulting telemetry/KPIs are written to the JSON file specified by `--out`.

 Troubleshooting:

 - If Blender cannot import modules from the repo, either install the addon into Blender's addons directory or pass `--repo-root` pointing to the project root (folder containing `Helper/` and `Operator/`).
 - Running headless still requires the addon/module code to be importable. If you installed the addon via Blender UI, the script should find the modules.

 Security:

 - The script will load any file passed via `--clip`. Only run with trusted clips.
