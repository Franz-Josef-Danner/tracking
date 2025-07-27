# Import operator modules via absolute paths
from tracking-main.operators.tracking import solver, camera, export

operator_classes = (
    *solver.operator_classes,
    *camera.operator_classes,
    *export.operator_classes,
)
