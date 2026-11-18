#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x runtime/5.2/python/bin/python3.13 ]; then
  exec runtime/5.2/python/bin/python3.13 launch.py "$@"
fi
if [ -x runtime/Blender.app/Contents/Resources/5.2/python/bin/python3.13 ]; then
  exec runtime/Blender.app/Contents/Resources/5.2/python/bin/python3.13 launch.py "$@"
fi
exec python3 launch.py "$@"
