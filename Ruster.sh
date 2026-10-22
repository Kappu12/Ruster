#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -x runtime/4.5/python/bin/python3.11 ]; then
  exec runtime/4.5/python/bin/python3.11 launch.py "$@"
fi
exec python3 launch.py "$@"
