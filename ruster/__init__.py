"""Rustmatics: a Rust-focused Blender application."""

__version__ = "0.13.0"


def register():
    from . import branding
    branding.register()
    from . import app
    app.register()


def unregister():
    from . import app
    app.unregister()
    from . import branding
    branding.unregister()
