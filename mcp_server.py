#!/usr/bin/env python3
"""Stdio entry point, invoked with bundled Python rather than Blender."""
from pathlib import Path
import site
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
if (ROOT/'python_modules').is_dir():
    sys.path.insert(0,str(ROOT/'python_modules'))
    # pywin32 registers its module and DLL directories through its .pth file.
    site.addsitedir(str(ROOT/'python_modules'))
if __name__=='__main__':
    from ruster.mcp_server import main
    main()
