import bpy
from ..Helper.bootstrap import run_bootstrap
from ..Helper.snapshot import snapshot_active_markers
from ..Helper.detect import detect_features
from ..Helper.newmarker import classify_markers
from ..Helper.cleaneup import cleanup_new_markers
from ..Helper.delete import delete_tracks_by_names
from ..Helper.marker_size import apply_marker_sizes

class KAISERLICHTRACKER_OT_detect_cycle(bpy.types.Operator):
    """Detect-Zyklus (vereinfachte Version) – bestehender Operator umgebaut laut Vorgabe.

    Pseudocode (Originalvorgabe, wortnah umgesetzt):
      bootstrap -> (Startwerte ma, md, pz, sz, tr, za, ug, og)
      while ...:
        detect (mit tr, md, ma)
        snapshot
        klassifizieren (alte vs neue marker)
        am = anzahl neue marker
        if am >= ug:
          if am <= og:
            cleanup (alte + neue, md)
            tr = tr * 2
            if tr > 1 => break (finished)
            else pz = pz * 0.3; sz = pz * 2; apply sizes; continue
          else (am > og):
            za = za * 0.82
            md = md / max(0.75, min(0.15, (za / am)))  # bewusst wortgetreu, mathematisch immer 0.75
            delete neue marker
            continue
        else (am < ug):
          md = md / max(-50, min(50, (za / am)))
          delete neue marker
          continue

    Sicherheits-Extras: max_iterations, Schutz gegen Division durch 0 und pz < 1.
    """
    bl_idname = "kaiserlich_tracker.detect_cycle"
    bl_label = "Detect Zyklus"
    bl_description = "Einfacher Detect Zyklus gemäß bereitgestelltem Pseudocode (Operator umgebaut)"
    bl_options = {"REGISTER", "INTERNAL"}

    max_iterations: bpy.props.IntProperty(  # type: ignore
        name="Max Iterationen",
        default=50,
        min=0,
        soft_max=500,
        description="0 = unendlich; Sicherheitslimit für Iterationen"
    )

    def execute(self, context):  # noqa: C901
        scene = context.scene
        ef = getattr(scene, 'kaiserlich_markers_per_frame', 0)

        params = run_bootstrap(context, ef)
        if not params:
            self.report({'WARNING'}, "Bootstrap fehlgeschlagen")
            return {'CANCELLED'}

        md = float(params['md'])
        ma = int(params['ma'])
        tr = float(params['tr'])
        za = float(params['za'])
        ug = int(params['ug'])
        og = int(params['og'])
        pz = int(params['pz'])
        sz = int(params['sz'])
        hz = int(params['hz'])
        vc = int(params['vc'])

        print("[Kaiserlich Tracker] ==== Detect Zyklus (umbau) Start ====")
        print(f"[Kaiserlich Tracker] ug={ug} og={og} za={za:.3f} md={md:.2f} tr={tr:.3f} pz={pz} sz={sz}")

        iterations = 0
        accepted = False
        total_deleted_cleanup = 0
        baseline = snapshot_active_markers(context)

        while True:
            iterations += 1
            if self.max_iterations > 0 and iterations > self.max_iterations:
                print(f"[Kaiserlich Tracker] Iterationslimit {self.max_iterations} erreicht – Abbruch.")
                break
            print(f"[Kaiserlich Tracker] -- Iteration {iterations} -- tr={tr:.4f} md={md:.2f} pz={pz} za={za:.3f}")

            detect_features(
                context,
                placement='FRAME',
                margin=ma,
                threshold=tr,
                min_distance=int(max(1, round(md)))
            )

            after = snapshot_active_markers(context)
            alte_marker, neue_marker = classify_markers(baseline, after)
            am = len(neue_marker)
            print(f"[Kaiserlich Tracker] Neue Marker roh (am) = {am}")

            if am >= ug:
                if am <= og:
                    print(f"[Kaiserlich Tracker] Im Korridor ({ug} <= {am} <= {og}) -> Cleanup & tr*2")
                    cleaned, deleted = cleanup_new_markers(
                        context,
                        alte_marker,
                        neue_marker,
                        md=md,
                        hz=hz,
                        vc=vc
                    )
                    total_deleted_cleanup += deleted
                    am = len(cleaned)
                    print(f"[Kaiserlich Tracker] Neue Marker nach Cleanup (am) = {am}")
                    if cleaned:
                        baseline.extend(cleaned)
                    tr *= 2.0
                    print(f"[Kaiserlich Tracker] Threshold verdoppelt: tr={tr:.4f}")
                    if tr > 1.0:
                        print("[Kaiserlich Tracker] tr > 1 -> fertig (break)")
                        accepted = True
                        break
                    else:
                        pz = max(1, int(round(pz * 0.3)))
                        sz = pz * 2
                        apply_marker_sizes(context.space_data.clip if getattr(context, 'space_data', None) else None, pz, sz)
                        print(f"[Kaiserlich Tracker] Pattern/Search angepasst pz={pz} sz={sz}")
                        continue
                else:
                    print(f"[Kaiserlich Tracker] Über OG: am={am} og={og} -> za*0.82 & md Formel1 & delete neue Marker")
                    za *= 0.82
                    ratio = (za / am) if am != 0 else 0.0
                    denom = max(0.75, min(0.15, ratio))
                    if denom == 0:
                        denom = 0.75
                    md = md / denom
                    print(f"[Kaiserlich Tracker] za={za:.3f} ratio={ratio:.5f} denom={denom:.5f} -> md={md:.2f}")
                    if neue_marker:
                        names = [m['track'] for m in neue_marker]
                        removed = delete_tracks_by_names(context, names)
                        print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (über OG)")
                    continue
            else:
                print(f"[Kaiserlich Tracker] Unter UG: am={am} ug={ug} -> md Formel2 & delete neue Marker")
                ratio = (za / am) if am != 0 else 0.0
                denom = max(-50, min(50, ratio))
                if denom == 0:
                    denom = 1.0
                md = md / denom
                print(f"[Kaiserlich Tracker] ratio={ratio:.5f} denom={denom:.5f} -> md={md:.2f}")
                if neue_marker:
                    names = [m['track'] for m in neue_marker]
                    removed = delete_tracks_by_names(context, names)
                    print(f"[Kaiserlich Tracker] {removed} neue Tracks gelöscht (unter UG)")
                continue

        final_snapshot = snapshot_active_markers(context)
        net_added = len(final_snapshot) - len(baseline)
        status = "Fertig" if accepted else "Abgebrochen"
        self.report({'INFO'}, f"{status}: Iterationen={iterations} net_added={net_added} md={md:.2f} tr={tr:.3f} pz={pz} cleanup_deleted={total_deleted_cleanup}")
        print("[Kaiserlich Tracker] ==== Detect Zyklus (umbau) Ende ====")
        return {'FINISHED'}

