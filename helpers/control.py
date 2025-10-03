from .delete import delete_marker
from .detect import _apply_pattern_size, _normalize_pattern_size


def control_cycle(context, new_marker_list, values):
    amount = len(new_marker_list)

    # ✅ Ziel erreicht
    if values["ug"] <= amount <= values["og"]:
        clip = context.edit_movieclip
        if clip:
            _apply_pattern_size(clip, _normalize_pattern_size(values["pz"]))
        print(f"[Kaiserlich] Cycle finished: {amount} Marker")
        return True

    # ❌ alle neuen Marker wieder löschen (Cleanup für Neustart)
    for nm in new_marker_list:
        delete_marker(nm)

    if amount < values["ug"]:
        # Zu wenige → Threshold runter, Pattern Size hoch
        values["tr"] *= 0.5
        if values["tr"] < 0.1:
            print("[Kaiserlich] Cycle finished (threshold floor reached)")
            return True
        values["pz"] *= 1.1
        return False
    else:
        # Zu viele → Min Distance erhöhen (skalierend zur Abweichung)
        scale = max(1.05, amount / max(1.0, values["za"]))
        values["md"] *= scale
        # Clamp gegen pathologisches Wachstum
        max_md = values["width"] * 0.25
        if values["md"] > max_md:
            values["md"] = max_md
        return False
