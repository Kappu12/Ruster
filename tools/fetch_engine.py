"""Fetch the pinned Linux test runtime; also used by CI."""
import json
from pathlib import Path
import sys
import tarfile
from package import fetch

root = Path(__file__).resolve().parents[1]
lock = json.loads((root/'engine.lock.json').read_text())
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
entry = lock['archives']['linux-x64']
archive = target/entry['file']
fetch(lock['base_url']+'/'+entry['file'], archive, entry['sha256'])
with tarfile.open(archive) as stream:
    stream.extractall(target, filter='data')
