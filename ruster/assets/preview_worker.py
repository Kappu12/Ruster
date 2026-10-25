"""Prepare one protected preview library without blocking the editor UI."""
import argparse
import json
from pathlib import Path
import sys
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',required=True,type=Path)
    parser.add_argument('--uid',required=True,type=int)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--parent-pid',type=int)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    from ruster.core.project import atomic_write
    try:
        from ruster.core.process_limits import protect_process,MIB
        protect_process(2048*MIB,args.parent_pid)
        import bpy
        from ruster import scene
        from ruster.core import wire
        scene.cache_dir=lambda:args.cache
        bpy.ops.wm.read_factory_settings(use_empty=True)
        obj=scene.root_object([wire.encode(2,0,args.uid)],bpy.context.scene.collection)
        if not scene.attach_visual(obj) or not obj.get('ruster_visual'):
            raise ValueError(obj.get('ruster_model_error','The cached asset has no model to prepare'))
        result={'asset_key':scene.model_asset_key(args.uid)}
    except Exception as error:
        traceback.print_exc()
        result={'error':str(error)}
    atomic_write(args.report,json.dumps(result).encode())
    if result.get('error'):raise RuntimeError(result['error'])


if __name__=='__main__':main()
