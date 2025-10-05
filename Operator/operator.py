import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.marker_size import apply_marker_sizes


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
    bl_label = "Detect Zyklus"  # Neuer Algorithmus laut Vorgabe ug/og Korridor
    bl_description = (
        "Iterativer Marker-Detect Zyklus gemäß Vorgabe: Bootstrap -> Detect -> Klassifikation -> Cleanup -> "
        "Korridorlogik (ug/og) mit dynamischer Anpassung von threshold, pattern/search-size und md."
    )
    bl_options = {"REGISTER", "INTERNAL"}

    max_iterations: bpy.props.IntProperty(  # type: ignore
        name="Max Iterationen",
        default=0,
        min=0,
        soft_max=100,
        description="0 oder kleiner = kein Limit; sonst maximale Anzahl Iterationen als Sicherheitsbremse"
    )

    finish_threshold: bpy.props.FloatProperty(  # type: ignore
        name="Finish Threshold (tr <)",
        default=0.01,
        min=0.0001,
        description="Schwellwert unter den der Threshold fallen muss um im Korridor final zu beenden"
    )

    corridor_tr_factor: bpy.props.FloatProperty(  # type: ignore
        name="Korridor Threshold Faktor",
        default=0.15,
        min=0.01,
        max=0.99,
        description="Faktor zur Multiplikation von tr wenn (ug < am < og)"
    )

    pattern_growth: bpy.props.FloatProperty(  # type: ignore
        name="Pattern Wachstumsfaktor",
        default=1.1,
        min=1.01,
        max=3.0,
        description="Multiplikator für pz im Korridor (wenn noch nicht fertig)"
    )

    def execute(self, context):
        scene = context.scene
        ef = scene.kaiserlich_markers_per_frame

        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        # Ausgangswerte aus Bootstrap
        md = float(params['md'])
        ma = int(params['ma'])
        tr = float(params['tr'])
        za = float(params['za'])
        ug = int(params['ug'])
        og = int(params['og'])
        pz = int(params['pz'])
        sz = int(params['sz'])

        hz = params['hz']
        vc = params['vc']

        # Baseline Snapshot (alle vorhandenen Marker vor Start)
        baseline = snapshot_active_markers(context)
        baseline_count = len(baseline)

        print("[Kaiserlich Tracker] ================ Detect Zyklus Start ================")
        print(f"[Kaiserlich Tracker] ug={ug} og={og} za={za:.2f} | Start md={md:.2f} tr={tr:.3f} pz={pz} sz={sz}")

        iterations = 0
        total_deleted_during_cleanup = 0
        accepted = False

        while (self.max_iterations <= 0) or (iterations < self.max_iterations):
            iterations += 1
            print(f"[Kaiserlich Tracker] ---- Iteration {iterations} ---- md={md:.2f} tr={tr:.4f} pz={pz} sz={sz}")

            # 1. Detect
            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )

            # 2. Snapshot danach
            after = snapshot_active_markers(context)

            # 3. Klassifikation (alte vs neue Marker)
            alte_marker, neue_marker_roh = classify_markers(baseline, after)

            # 4. Cleanup Abstand md
            cleaned_new, deleted = cleanup_new_markers(
                context,
                alte_marker,
                neue_marker_roh,
                md=md,
                hz=hz,
                vc=vc
            )
            total_deleted_during_cleanup += deleted
            am = len(cleaned_new)
            print(f"[Kaiserlich Tracker] Anzahl neue Marker nach Cleanup (am): {am}")

            # 5. Korridor Logik
            if am > ug:
                # Wir liegen über Untergrenze
                if am < og:
                    # Im Korridor (zwischen ug und og)
                    print(f"[Kaiserlich Tracker] Im Korridor: ug < am ({am}) < og. Versuche Verfeinerung.")
                    tr *= self.corridor_tr_factor
                    print(f"[Kaiserlich Tracker] Threshold reduziert: neuer tr={tr:.5f}")
                    if tr < self.finish_threshold:
                        print(f"[Kaiserlich Tracker] tr ({tr:.5f}) < Finish ({self.finish_threshold}) -> Fertig.")
                        accepted = True
                        # Neue Marker behalten -> Baseline erweitern & Abbruch
                        baseline.extend(cleaned_new)
                        break
                    else:
                        # Pattern/Search Größe erhöhen
                        pz = max(1, int(round(pz * self.pattern_growth)))
                        sz = pz * 2
                        apply_marker_sizes(context.space_data.clip if getattr(context, 'space_data', None) else None, pz, sz)
                        print(f"[Kaiserlich Tracker] Pattern/Search angepasst: pz={pz} sz={sz}")
                        # akzeptiere bisherige neue Marker & erweitere Baseline, dann weiter sammeln
                        if cleaned_new:
                            baseline.extend(cleaned_new)
                        # Weiter zur nächsten Iteration ohne Löschen
                        continue
                else:
                    # am >= og => zu viele neue Marker -> md adjust & neue verwerfen
                    print(f"[Kaiserlich Tracker] Über OG: am ({am}) >= og ({og}) -> md anpassen & neue löschen.")
                    md = _recompute_md(md, za, am)
                    print(f"[Kaiserlich Tracker] md angepasst (über OG): {md:.2f}")
                    if cleaned_new:
                        names = [m['track'] for m in cleaned_new]
                        removed = delete_tracks_by_names(context, names)
                        print(f"[Kaiserlich Tracker] {removed} neue Tracks verworfen (über OG).")
                    continue
            else:
                # am <= ug -> unter Untergrenze -> md anpassen & neue löschen (wir wollen mehr, also verwerfen & Param anpassen)
                print(f"[Kaiserlich Tracker] Unter UG: am ({am}) <= ug ({ug}) -> md anpassen & neue löschen.")
                md = _recompute_md(md, za, am)
                print(f"[Kaiserlich Tracker] md angepasst (unter UG): {md:.2f}")
                if cleaned_new:
                    names = [m['track'] for m in cleaned_new]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks verworfen (unter UG).")
                continue

            # Falls wir hier landen wäre das eine Sicherheits-Situation (sollte nicht passieren)
            print("[Kaiserlich Tracker] Warnung: Unerwarteter Pfad – keine Regel angewandt.")

        else:
            if self.max_iterations > 0:
                print(f"[Kaiserlich Tracker] Iterationslimit ({self.max_iterations}) erreicht – Abbruch.")

        final_snapshot = snapshot_active_markers(context)
        final_total = len(final_snapshot)
        added_effective = final_total - baseline_count

        status = "Abgeschlossen" if accepted else ("Limit erreicht" if self.max_iterations > 0 and iterations >= self.max_iterations else "Abbruch")
        self.report({'INFO'}, (
            f"{status}: Iterationen={iterations} | Effektiv hinzugefügt={added_effective} | md={md:.2f} | tr={tr:.5f} | pz={pz} | Cleanup gelöscht Summe={total_deleted_during_cleanup} | Gesamt={final_total}"
        ))
        print("[Kaiserlich Tracker] ================ Detect Zyklus Ende =================")
        return {'FINISHED'}
