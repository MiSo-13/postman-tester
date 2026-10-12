"""Postman Tester entry point: choose Qt platform before importing PyQt6."""
import os
import sys


def configure_qt_platform(argv=None, *, platform=None):
    """Default Linux to XWayland; preserve explicit Qt platform overrides."""
    argv = sys.argv if argv is None else argv
    platform = sys.platform if platform is None else platform
    if "--x11" in argv:
        argv.remove("--x11")
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    elif platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


if __name__ == "__main__":
    configure_qt_platform()
    from app.main_window import launch
    raise SystemExit(launch())
