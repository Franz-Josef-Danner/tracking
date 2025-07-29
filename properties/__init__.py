# Relative imports for property modules
from . import tracking_props, props_extra


def register_properties():
    tracking_props.register_props()
    props_extra.register_props()


def unregister_properties():
    props_extra.unregister_props()
    tracking_props.unregister_props()
