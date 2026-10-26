"""Check an offline Cpp2IL metadata report against the native bridge's bindings.

Never loads a game binary or inspects a running client. The report is produced by
static file analysis; matching metadata is not proof of in-game compatibility.
"""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def contracts(source):
    pattern = r'\{"([^"]+)", "([^"]+)", "([^"]+)", "([^"]+)", (true|false), \{([^}]*)\}, &\w+\}'
    return [(role, owner, member, result, static == 'true', re.findall(r'"([^"]+)"', parameters))
        for role, owner, member, result, static, parameters in re.findall(pattern, source)]


def check(report, source):
    bindings = contracts(source)
    if not bindings:raise ValueError('No native API binding contracts found')
    methods = [];owner = '';singleton = 0
    for line in report.splitlines():
        if line.startswith('TYPE\t'):owner = line.split('\t')[2]
        if owner == 'Bootstrap+<>c' and line.startswith('FIELD\t'):
            _, flags, kind, name = line.split('\t')
            if name == '<>9' and kind == owner and 'Static' in flags:singleton += 1
        if line.startswith('METHOD\t'):
            _, flags, signature = line.split('\t')
            methods.append((owner, 'Static' in flags, signature))
    failures = []
    for role, owner, name, result, static, parameters in bindings:
        prefix = result+' '+owner+'::'+name+'('
        candidates = [s for o, st, s in methods if o == owner and st == static and s.startswith(prefix)]
        matched = []
        for candidate in candidates:
            arguments = candidate[len(prefix):-1]
            # These bridge contracts use only non-generic argument types.
            actual = [value.rsplit(' ', 1)[0] for value in arguments.split(', ')] if arguments else []
            if actual == parameters:matched.append(candidate)
        if len(matched) != 1:failures.append(f'{role}: {len(matched)} matches')
    loaders = [s for owner, static, s in methods if owner == 'Bootstrap+<>c' and not static
        and re.fullmatch(r'UnityEngine.GameObject Bootstrap\+<>c::<Init_Tier0>b__\w+\(System.String [^ )]+\)', s)]
    if len(loaders) != 1:failures.append(f'typed bootstrap loader: {len(loaders)} matches')
    if singleton != 1:failures.append(f'bootstrap singleton: {singleton} matches')
    if not any(line.endswith('\tBaseNetworkable') for line in report.splitlines() if line.startswith('TYPE\t')):
        failures.append('BaseNetworkable type missing')
    if failures:raise ValueError('; '.join(failures))
    return len(bindings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-report', type=Path, required=True)
    args = parser.parse_args()
    total = check(args.metadata_report.read_text(), (ROOT/'ruster/preview_native/client.cpp').read_text())
    print(f'Offline API metadata matches: {total} Unity methods, one typed prefab loader and singleton. No Rust process used.')
