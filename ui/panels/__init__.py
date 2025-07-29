# Relative imports for panel modules
from . import tracking_panel, settings_panel, panels_extra

panel_classes = (
    *tracking_panel.panel_classes,
    *settings_panel.panel_classes,
    *panels_extra.panel_classes,
)
