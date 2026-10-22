"""Ruster: a Rust-focused Blender application."""

__version__ = "0.8.0"


def register():
    from . import app
    app.register()


def unregister():
    from . import app
    app.unregister()
