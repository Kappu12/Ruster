"""Readable catalog names shared by search and placement feedback."""
from pathlib import PurePosixPath
import re


def display_name(path):
    stem=re.sub(r'\.prefab$','',PurePosixPath(path).name,flags=re.IGNORECASE)
    match=re.fullmatch(r'cube_(.+)_dev_(\d+)',stem,re.IGNORECASE)
    if match:return f'Dev Cube {re.sub(r"[._-]+", " ", match[1]).title()} {match[2]}'
    name=re.sub(r'[._-]+',' ',stem).strip()
    if '/sound/' in path.lower():name+=' (Sound effect)'
    return name
