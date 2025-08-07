import bpy
import json
import os
from datetime import datetime

def get_log_path():
    # Verwende Tempdir, wenn keine .blend-Datei geöffnet ist
    if not bpy.data.is_saved:
        return os.path.join(bpy.app.tempdir, "tracking_addon_log.json")
    return bpy.path.abspath("//tracking_addon_log.json")

def write_log_entry(event_type, message, **kwargs):
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "message": message,
        "data": kwargs
    }

    log_path = get_log_path()

    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        else:
            log_data = []

        log_data.append(log_entry)

        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)

    except Exception as e:
        print(f"⚠️ Fehler beim Schreiben des Logs: {e}")
