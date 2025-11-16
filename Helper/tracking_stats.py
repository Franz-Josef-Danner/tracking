# ======================================================================
# File: Helper/tracking_stats.py
# Kaiserlich Tracker – KPI Tracking Helper
# ======================================================================

import bpy

# Namen der Scene-Keys (einheitlich & zentral, kein Duplicate-Risk)
KEY_DX = "kaiserlich_dx_var_list"
KEY_DY = "kaiserlich_dy_var_list"
KEY_REL = "kaiserlich_rel_var_list"
KEY_GLOB_P = "kaiserlich_global_p_dev_list"
KEY_P_DEV = "kaiserlich_p_dev_list"


# ----------------------------------------------------------------------
# Initialize Tracking Stats (AM ANFANG EINES GESAMTEN TRACKING-RUNS)
# ----------------------------------------------------------------------
def tracking_stats_init(scene: bpy.types.Scene) -> None:
    scene[KEY_DX] = []
    scene[KEY_DY] = []
    scene[KEY_REL] = []
    scene[KEY_GLOB_P] = []
    scene[KEY_P_DEV] = []
    print("[KPI] Stats initialized")


# ----------------------------------------------------------------------
# Append values during tracking (FRAME-WEISE)
# Diese Funktion wird von apply_formula_on_selected_tracks aufgerufen
# ----------------------------------------------------------------------
def tracking_stats_accumulate(scene: bpy.types.Scene,
                              dx_var: float,
                              dy_var: float,
                              rel_var: float,
                              global_p_dev: float,
                              avg_p_dev: float) -> None:
    try:
        scene[KEY_DX].append(dx_var)
        scene[KEY_DY].append(dy_var)
        scene[KEY_REL].append(rel_var)
        scene[KEY_GLOB_P].append(global_p_dev)
        scene[KEY_P_DEV].append(avg_p_dev)
    except KeyError:
        print("[KPI][Error] Stats list missing → run tracking_stats_init first")


# ----------------------------------------------------------------------
# Final evaluation when tracking ENDET
# ----------------------------------------------------------------------
def tracking_stats_finalize(scene: bpy.types.Scene) -> None:
    dx_list = scene.get(KEY_DX, [])
    dy_list = scene.get(KEY_DY, [])
    rel_list = scene.get(KEY_REL, [])
    gp_list = scene.get(KEY_GLOB_P, [])
    p_list = scene.get(KEY_P_DEV, [])

    if not dx_list or not gp_list:
        print("[KPI] No stats collected → skip finalize")
        return

    avg_dx = sum(dx_list) / len(dx_list)
    avg_dy = sum(dy_list) / len(dy_list)
    avg_rel = sum(rel_list) / len(rel_list)
    avg_global_p = sum(gp_list) / len(gp_list)
    avg_p = sum(p_list) / len(p_list)

    print("\n[KPI][FINAL] Tracking Statistics =====================================")
    print(f"  Avg dx_var       : {avg_dx:.6f}")
    print(f"  Avg dy_var       : {avg_dy:.6f}")
    print(f"  Avg rel_var      : {avg_rel:.6f}")
    print(f"  Avg global_p_dev : {avg_global_p:.6f}")
    print(f"  Avg per_m_dev    : {avg_p:.6f}")
    print("=====================================================================\n")

    # Für UI/Weiterverarbeitung im Scene speichern
    scene["kaiserlich_stats_last"] = {
        "avg_dx_var": avg_dx,
        "avg_dy_var": avg_dy,
        "avg_rel_var": avg_rel,
        "avg_global_p_dev": avg_global_p,
        "avg_p_dev": avg_p,
    }

    # Cleanup → ready für nächsten Lauf
    tracking_stats_init(scene)
