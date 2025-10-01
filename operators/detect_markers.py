import bpy
from bpy.props import (  # type: ignore
    BoolProperty,
    FloatProperty,
    IntProperty,
)
from ..helpers.detect_helper import detect_features_multipass


class TRACKING_OT_detect_markers(bpy.types.Operator):
    bl_idname = "tracking.detect_markers"
    bl_label = "Detect Markers"
    bl_description = (
        "Mehrfaches Feature-Detect: Startet bei Threshold=1.0 und halbiert bis < 0.1.\n"
        "So werden erst sehr starke, dann moderat schwaechere Features hinzugefuegt (frueher <0.0001)."
    )
    bl_options = {"REGISTER", "UNDO"}

    # --- Optionen (Annotation Syntax gegen _PropertyDeferred Probleme) ---
    remove_duplicates: BoolProperty = BoolProperty(
        name="Duplikate entfernen",
        default=True,
        description="Marker mit Distanz <= Duplikat-Toleranz oder ohne Distanz (ab zweitem) entfernen",
    )
    duplicate_tolerance: FloatProperty = FloatProperty(
        name="Duplikat Tol (px)",
        default=0.5,
        min=0.0,
        description="Maximaler Pixelabstand fuer exakt gleiche Marker (0 = nur identisch)",
    )
    keep_first_marker: BoolProperty = BoolProperty(
        name="Ersten behalten",
        default=True,
        description="Ersten erkannten Marker niemals als Duplikat loeschen",
    )
    immediate_delete: BoolProperty = BoolProperty(
        name="Sofort loeschen",
        default=False,
        description="Duplikate nicht am Ende im Batch, sondern direkt beim Erkennen loeschen (instabiler)",
    )
    cluster_consolidate: BoolProperty = BoolProperty(
        name="Cluster konsolidieren",
        default=True,
        description="Raeumlich nahe Marker zusaetzlich clustern und zusammenfassen",
    )
    cluster_tolerance_px: FloatProperty = FloatProperty(
        name="Cluster Tol (px)",
        default=6.0,
        min=0.0,
        description="Radius fuer Cluster-Zuordnung (Pixel)",
    )
    cluster_max_per_cluster: IntProperty = IntProperty(
        name="Max/Cluster",
        default=1,
        min=1,
        description="Wie viele Marker pro Cluster behalten werden",
    )
    max_new_markers: IntProperty = IntProperty(
        name="Max Marker",
        default=7,
        min=1,
        max=100,
        description="Maximalzahl neu hinzuzufügender Marker (hartes Limit)",
    )

    def draw(self, context):  # noqa: D401
        layout = self.layout
        col = layout.column(align=True)
        col.label(text="Duplikate:")
        if not hasattr(self, "remove_duplicates"):
            col.label(text="[WARN] Properties nicht registriert", icon='ERROR')
            return
        col.prop(self, "remove_duplicates")
        sub = col.column(align=True)
        try:
            sub.enabled = bool(self.remove_duplicates)
        except Exception:  # noqa: BLE001
            sub.enabled = True
        sub.prop(self, "duplicate_tolerance")
        sub.prop(self, "keep_first_marker")
        sub.prop(self, "immediate_delete")
        col.separator()
        col.label(text="Cluster:")
        col.prop(self, "cluster_consolidate")
        sub2 = col.column(align=True)
        try:
            sub2.enabled = bool(self.cluster_consolidate)
        except Exception:  # noqa: BLE001
            sub2.enabled = True
        sub2.prop(self, "cluster_tolerance_px")
        sub2.prop(self, "cluster_max_per_cluster")
        col.separator()
        col.label(text="Limit:")
        col.prop(self, "max_new_markers")

    def execute(self, context):
        result = detect_features_multipass(
            context,
            remove_duplicates=self.remove_duplicates,
            duplicate_tolerance_px=self.duplicate_tolerance,
            keep_first_marker=self.keep_first_marker,
            immediate_delete=self.immediate_delete,
            cluster_consolidate=self.cluster_consolidate,
            cluster_tolerance_px=self.cluster_tolerance_px,
            cluster_max_per_cluster=self.cluster_max_per_cluster,
            max_new_markers=self.max_new_markers,
        )
        if not result.get('success'):
            # Erweiterte Diagnoseausgaben, falls vorhanden
            etype = result.get('exception_type')
            tb = result.get('traceback')
            if etype:
                print(f"[TrackingHelper][ERROR] exception_type={etype}")
            if tb:
                print("[TrackingHelper][TRACEBACK]\n" + tb)
            self.report({'ERROR'}, result.get('message', 'Unbekannter Fehler'))
            return {'CANCELLED'}
        passes = result.get('passes', 0)
        total_added = result.get('total_added', -1)  # effektive Netto-Anzahl
        per_pass = result.get('per_pass', [])
        raw_total = result.get('raw_total_added', None)

        summary_parts = []
        for thr, added, note in per_pass:
            base = f'{thr:.5f}:{added}'
            if note:
                base += f' ({note})'
            summary_parts.append(base)
        summary = ', '.join(summary_parts) if summary_parts else 'keine Marker hinzugefuegt'

        removed_dup = result.get('removed_duplicate_count', 0)
        removed_cluster = result.get('cluster_removed_count', 0)
        removed_limit = result.get('max_limit_removed_count', 0)
        extra = []
        if removed_dup:
            extra.append(f'Dupl:{removed_dup}')
        if removed_cluster:
            extra.append(f'Cluster:{removed_cluster}')
        if removed_limit:
            extra.append(f'Limit:{removed_limit}')
        info_tail = (' | ' + ', '.join(extra)) if extra else ''
        msg = f'{passes} Durchlaeufe, hinzugefuegt: {total_added} (pro Pass: {summary}){info_tail}'
        if raw_total is not None and raw_total != total_added:
            msg += f' | raw_total:{raw_total}'
        self.report({'INFO'}, msg)
        return {'FINISHED'}
