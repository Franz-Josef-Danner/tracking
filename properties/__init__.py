# Absolute imports for property modules
from tracking-main.properties import tracking_props, test_props


def register_properties():
    tracking_props.register_props()
    test_props.register_props()


def unregister_properties():
    test_props.unregister_props()
    tracking_props.unregister_props()
