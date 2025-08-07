import bpy
import json
import os
from datetime import datetime

LOG_FILE_PATH = bpy.path.abspath("//tracking_addon_log.json")

def write_log_entry(event_type, message, **kwargs):
    if not bpy.data.is_saved:
        print("⚠️ Kein Projekt gespeichert – Log wird übersprungen.")
        return

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": event_type,
        "message": message,
        "data": kwargs
    }

    try:
        if os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
        else:
            log_data = []

        log_data.append(log_entry)

        with open(LOG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)

    except Exception as e:
        print(f"⚠️ Fehler beim Schreiben des Logs: {e}")
