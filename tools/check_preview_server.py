"""Compile the server companion and test its pure decoder without starting Rust."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from build_preview_client import ROOT, protocol_cases, peer_cases


def check(server):
    sdks = subprocess.check_output(['dotnet', '--list-sdks'], text=True).splitlines()
    version, location = sdks[-1].split(' ', 1)
    compiler = Path(location.strip('[]'))/version/'Roslyn/bincore/csc.dll'
    runtimes = [line.split(' ', 2) for line in subprocess.check_output(['dotnet', '--list-runtimes'], text=True).splitlines()
                if line.startswith('Microsoft.NETCore.App ')]
    _, runtime, location = runtimes[-1]
    framework = Path(location.strip('[]'))/runtime
    source = ROOT/'ruster/preview_native'
    with tempfile.TemporaryDirectory(dir=ROOT/'build', prefix='preview-managed-') as folder:
        folder = Path(folder);binary = folder/'decoder.dll'
        command = ['dotnet', str(compiler), '-nologo', '-noconfig', '-nostdlib+', '-nowarn:0649']
        references = [framework/name for name in ('System.Private.CoreLib.dll', 'System.Runtime.dll',
            'System.Console.dll', 'System.Collections.dll')]
        subprocess.run(command+['-target:exe', '-out:'+str(binary)]+['-reference:'+str(p) for p in references]
            +[str(source/'PreviewProtocol.cs'), str(ROOT/'tests/preview_protocol_managed.cs')], check=True)
        binary.with_suffix('.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'tfm': 'net'+'.'.join(runtime.split('.')[:2]),
            'framework': {'name': 'Microsoft.NETCore.App', 'version': runtime}}}))
        path = folder/'snapshot.bin'
        for data, expected in protocol_cases():
            path.write_bytes(data)
            result = subprocess.run(['dotnet', str(binary), str(path)], capture_output=True)
            if result.returncode != expected:raise RuntimeError('Managed protocol check failed: '+result.stderr.decode(errors='replace'))
        subprocess.run(['dotnet',str(binary),'--peer',str(path)],check=True)
        if path.read_bytes()!=peer_cases()[0][0]:raise RuntimeError('Managed/native connection proof encoding differs')
        refs = list((server/'RustDedicated_Data/Managed').glob('*.dll'))+list((server/'carbon/managed').glob('*.dll'))+list((server/'carbon/managed/lib').glob('*.dll'))
        byname = {p.name:p for p in refs if p.name != '0Harmony.dll'}
        if not byname:raise ValueError('No dedicated-server reference assemblies found')
        # Compile the identical single-file plugin that the installer publishes.
        combined = folder/'RusterPreview.cs'
        combined.write_bytes((source/'RusterPreview.cs').read_bytes()+b'\n'+(source/'PreviewProtocol.cs').read_bytes())
        subprocess.run(command+['-target:library', '-out:'+str(folder/'RusterPreview.dll')]
            +['-reference:'+str(p) for p in byname.values()]+[str(combined)], check=True)
    print('Server plugin compilation and managed protocol checks passed (no Rust process used)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', type=Path, required=True)
    check(parser.parse_args().server)
