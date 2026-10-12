"""Postman Tester entry point.

Use `python main.py --x11` on Linux when the Wayland compositor disconnects
during Qt modal dialogs. Qt platform selection must happen before PyQt6 import.
"""
import os
import sys


def configure_qt_platform(argv=None):
    argv = sys.argv if argv is None else argv
    if "--x11" in argv:
        argv.remove("--x11")
        os.environ["QT_QPA_PLATFORM"] = "xcb"


if __name__ == "__main__":
    configure_qt_platform()
    from app.main_window import launch
    raise SystemExit(launch())
