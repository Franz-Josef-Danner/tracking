import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import diff_markers, classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names


def _recompute_md(current_md: float, za: float, am: int) -> float:
    """Berechnet neues md gemäß Vorgabe: md / (za / am) => md * am / za.

    Schutz vor Division durch 0 und zu kleinen Werten. Falls am == 0 wird ein
    konservativer Reduktionsfaktor angewandt.
    """
    if am <= 0 or za <= 0:
        return max(1.0, current_md * 0.5)
    new_md = current_md * (am / za)
    return max(1.0, new_md)

class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Zyklus"
    bl_description = "Iterativer Marker-Detect Zyklus gemäß Algorithmus (Bootstrap -> Mehrfach Detect bis Untergrenze erreicht)."
    bl_options = {"REGISTER", "INTERNAL"}

    max_iterations: bpy.props.IntProperty(  # type: ignore
        name="Max Iterationen",
        default=6,
        min=1,
        soft_max=15,
        description="Sicherheitslimit für Zyklen, um Endlosschleifen zu vermeiden"
    )

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame

        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        md = float(params['md'])  # dynamisch anpassbar
        ma = int(params['ma'])
        tr = float(params['tr'])
        za = float(params['za'])
        ug = int(params['ug'])  # Untergrenze Zielkorridor

        # Baseline (alte Marker) zu Beginn – bleibt bestehen, solange wir Schleifen fahren
        baseline = snapshot_active_markers(context)
        baseline_count = len(baseline)

        print("[Kaiserlich Tracker] ================ Detect Zyklus Start ================")
        print(f"[Kaiserlich Tracker] Ziel Untergrenze (ug): {ug} | za: {za:.2f} | Start md: {md:.2f}")

        final_new_markers = []
        total_deleted_during_cleanup = 0
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1
            print(f"[Kaiserlich Tracker] ---- Iteration {iterations} (md={md:.2f}) ----")

            # Detect
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(md)
            )

            # Snapshot nach Detect
            after = snapshot_active_markers(context)

            # Klassifikation relativ zur Baseline
            alte_marker, neue_marker_roh = classify_markers(baseline, after)

            # Cleanup (entfernt zu nahe neue Marker)
            cleaned_new, deleted = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker_roh,
                md=md,
                hz=params['hz'],
                vc=params['vc']
            )
            total_deleted_during_cleanup += deleted

            # Logging roher Diff (optional)
            _ = diff_markers(baseline, after)

            am = len(cleaned_new)  # Anzahl der neuen (bereinigten) Marker in diesem Durchlauf
            print(f"[Kaiserlich Tracker] Neue Marker nach Cleanup (am): {am}")

            # Abbruchbedingung laut Vorgabe: am > ug -> break
            if am > ug:
                print(f"[Kaiserlich Tracker] Abbruch: am ({am}) > ug ({ug}) – akzeptiere neue Marker.")
                final_new_markers = cleaned_new
                break

            # Sonst md neu berechnen und neue Marker wieder entfernen, um frischen Versuch zu starten
            new_md = _recompute_md(md, za, am)
            print(f"[Kaiserlich Tracker] md Anpassung: alt={md:.2f} -> neu={new_md:.2f} (Formel md*(am/za))")
            md = new_md

            # Neue Marker dieses Versuchs entfernen (Tracks löschen), damit nächste Iteration wieder von Baseline ausgeht
            if cleaned_new:
                names_to_delete = [m['track'] for m in cleaned_new]
                removed = delete_tracks_by_names(context, names_to_delete)
                print(f"[Kaiserlich Tracker] Rücksetzung: {removed} neue Tracks gelöscht für nächste Iteration.")
            else:
                print("[Kaiserlich Tracker] Keine neuen Marker zu löschen.")

        else:
            # while ohne Break -> Limit erreicht
            print(f"[Kaiserlich Tracker] Iterationslimit ({self.max_iterations}) erreicht – letzter Satz neuer Marker wird verworfen.")

        # Zusammenfassung
        final_snapshot = snapshot_active_markers(context)
        final_total = len(final_snapshot)
        added_effective = final_total - baseline_count
        self.report({'INFO'}, (
            f"Zyklus Ende nach {iterations} Iterationen | Effektiv hinzugefügt: {added_effective} | "
            f"Letzte md: {md:.2f} | Cleanup gelöschte in Summe: {total_deleted_during_cleanup} | Gesamt jetzt: {final_total}"
        ))
        print("[Kaiserlich Tracker] ================ Detect Zyklus Ende =================")
        return {'FINISHED'}
