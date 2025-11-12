# Helper/save_copy_helper.py
import bpy
from pathlib import Path
from datetime import datetime

def save_copy_to_project_backup(
    subdir_name: str = "KT_backup",
    suffix: str = "_backup",
    compress: bool = True
) -> str:
    """
    Speichert eine Kopie der aktuellen .blend-Datei in <Projektverzeichnis>/<subdir_name>.
    Die aktive Datei bleibt unverändert (copy=True).

    Args:
        subdir_name (str): Name des Backup-Unterordners im Projektverzeichnis (Default: "KT_backup").
        suffix (str): Suffix für den Dateinamen (z. B. "_backup").
        compress (bool): Komprimierte .blend speichern.

    Returns:
        str: Vollständiger Pfad zur gespeicherten Kopie.

    Raises:
        RuntimeError: Wenn die aktuelle Datei noch nie gespeichert wurde.
    """
    # Aktuelle .blend muss bereits gespeichert sein
    src_path = bpy.data.filepath
    if not src_path:
        raise RuntimeError(
            "[SaveCopy] Datei wurde noch nie gespeichert. "
            "Bitte zuerst regulär speichern (File > Save) und erneut ausführen."
        )

    src = Path(src_path)
    project_dir = src.parent
    backup_dir = project_dir / subdir_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_name = f"{src.stem}{suffix}_{timestamp}.blend"
    target_path = backup_dir / target_name

    # Kopie schreiben, aktive Datei unverändert lassen
    bpy.ops.wm.save_as_mainfile(
        filepath=str(target_path),
        check_existing=False,
        compress=compress,
        relative_remap=True,
        copy=True,
    )

    return str(target_path)