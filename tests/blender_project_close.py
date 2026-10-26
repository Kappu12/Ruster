"""Ruster savepoints follow document changes, never the private .blend flag."""
import os, sys, tempfile, traceback
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
if '--' in sys.argv:sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import ruster
from ruster import app, scene, studio, quitting, placement
from ruster.core import wire


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-close-') as temporary:
        directory = Path(temporary)
        os.environ['RUSTER_USER_DIR'] = str(directory/'user')
        ruster.register();studio.new_prefab()
        assert not quitting.has_unsaved_changes()
        root = scene.root_object([wire.encode(2, 0, 42)], bpy.context.scene.collection)
        assert quitting.has_unsaved_changes()
        target = directory/'Saved Project.ruster'
        assert bpy.ops.ruster.save(filepath=str(target)) == {'FINISHED'}
        assert target.is_file() and not quitting.has_unsaved_changes()
        quitting.status_tick()
        assert quitting.save_status() == 'Saved'
        root.location.x = 5
        assert quitting.has_unsaved_changes()
        quitting.status_tick()
        assert quitting.save_status() == 'Unsaved changes'
        root.location.x = 0
        assert not quitting.has_unsaved_changes(), 'Restoring the saved transform still prompts'
        quitting.status_tick()
        assert quitting.save_status() == 'Saved'
        # Preview state and native Blender's dirty bit are not project edits.
        root['ruster_model_status'] = 'Loading model'
        root['ruster_model_error'] = 'A cached preview is not available'
        scene.name_prefab(root, 'assets/models/generated_model_name.prefab')
        root.select_set(True);bpy.context.scene.cursor.location.x = 50
        assert not quitting.has_unsaved_changes()
        root.name = 'My custom name'
        assert quitting.has_unsaved_changes()
        app.save_project(target)
        root['ruster_symmetry_center'] = [0., 0., 0.]
        assert quitting.has_unsaved_changes()
        app.save_project(target)
        bpy.context.scene.ruster_construction.symmetry = True
        assert quitting.has_unsaved_changes(), 'Symmetry configuration was ignored'
        app.save_project(target)
        bpy.context.scene.ruster_construction.symmetry = False
        assert quitting.has_unsaved_changes()
        app.save_project(target)
        group = placement.group([root], 'My group')
        assert quitting.has_unsaved_changes()
        app.save_project(target)
        text = bpy.data.texts.new('Imported source')
        text.write('original');group['ruster_prefab_source'] = text.name
        app.save_project(target)
        text.write(' edited')
        assert quitting.has_unsaved_changes(), 'IO/source metadata edits were ignored'
        app.save_project(target)
        # Recovery and failed Save As must leave the manual savepoint intact.
        group.location.z += 2
        app.save_project(directory/'recovery.ruster', update_path=False)
        assert quitting.has_unsaved_changes()
        assert Path(bpy.context.scene.ruster.project_path).samefile(target)
        native_save = app.project.save
        def fail(*args, **kwargs):raise OSError('Simulated full disk')
        app.project.save = fail
        try:
            try:app.save_project(directory/'Failed.ruster')
            except OSError:pass
            else:raise AssertionError('Failed save reported success')
            assert quitting.has_unsaved_changes()
            assert Path(bpy.context.scene.ruster.project_path).samefile(target)
        finally:app.project.save = native_save
        app.save_project(target)
        expected = [(obj.name, obj.location.copy()) for obj in scene.prefab_roots()]
        app.request_missing_visuals = lambda objects:None
        app.open_path(target)
        assert not quitting.has_unsaved_changes(), 'A reopened .ruster immediately prompts'
        assert [(obj.name, obj.location) for obj in scene.prefab_roots()] == expected
        target.unlink()
        assert quitting.has_unsaved_changes(), 'A deleted save must offer to save again'
        # Close-after-save is armed only after a successful archive write.
        decisions = [];native_quit = quitting.schedule_quit
        quitting.schedule_quit = lambda:decisions.append('quit')
        try:
            assert bpy.ops.ruster.save(filepath=str(target), quit_after_save=True) == {'FINISHED'}
            assert decisions == ['quit'] and not quitting.has_unsaved_changes()
            app.project.save = fail
            try:bpy.ops.ruster.save(filepath=str(target), quit_after_save=True)
            except RuntimeError:pass  # An ERROR report propagates through bpy.ops.
            assert decisions == ['quit'], 'Save failure closed the editor'
        finally:
            quitting.schedule_quit = native_quit;app.project.save = native_save
        # New/Open continue only after a successful project save. A failed
        # save leaves the current document and requested destination untouched.
        continuations = [];native_schedule = quitting.schedule_action
        quitting.schedule_action = lambda action, filepath='':continuations.append((action, filepath))
        try:
            scene.prefab_roots()[0].location.y += 3
            assert bpy.ops.ruster.save(filepath=str(target), after_save='NEW') == {'FINISHED'}
            assert continuations == [('NEW', '')]
            assert bpy.ops.ruster.save(filepath=str(target), after_save='OPEN', next_filepath='next.ruster') == {'FINISHED'}
            assert continuations[-1] == ('OPEN', 'next.ruster')
            app.project.save = fail
            try:bpy.ops.ruster.save(filepath=str(target), after_save='NEW')
            except RuntimeError:pass
            assert len(continuations) == 2, 'Save failure replaced the document'
            app.project.save = native_save
            assert quitting.confirm_replacement('NEW') == {'FINISHED'}
            assert not bpy.context.scene.objects, 'Clean New still prompted'
            assert quitting.save_status() == 'Not saved yet'
        finally:
            quitting.schedule_action = native_schedule;app.project.save = native_save
        studio.new_prefab()
        assert not quitting.has_unsaved_changes()
        ruster.unregister()
    print('RUSTER_PROJECT_CLOSE_STATE_OK', flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
