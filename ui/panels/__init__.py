# Absolute imports for panel modules
from tracking_main.ui.panels import tracking_panel, settings_panel, test_panels

panel_classes = (
    *tracking_panel.panel_classes,
    *settings_panel.panel_classes,
    *test_panels.panel_classes,
)
