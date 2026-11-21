#!/usr/bin/env python3
"""SMのM-only mailboxページと整合する試験用Linux DTBを開発PCで生成する。

対象はJupiter2の既知のmailbox0..3の4ノードだけ。有効なmboxes利用者が
存在すれば変更を拒否する。元DTBを置換せず、他ノードと未知のプロパティを保持する。
この限定検査はLinux/Enclaveの実機動作や全PMP領域の適合を保証しない。
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


def load_fit_parser():
    path = Path(__file__).with_name('build-jupiter2-ram-boot-image.py')
    spec = importlib.util.spec_from_file_location('jupiter2_fdt', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nodes_with_status(fit, root):
    nodes = {}

    def walk(node, path, parent_enabled):
        enabled = parent_enabled and ('status' not in node.props or
                                      fit.string(node, 'status') in ('okay', 'ok'))
        nodes[path] = (node, enabled)
        for name, child in node.children.items():
            walk(child, path.rstrip('/') + '/' + name, enabled)

    walk(root, '/', True)
    return nodes


def fdt_metadata(data):
    header = struct.unpack_from('>10I', data)
    offset = header[4]
    reservations = []
    while offset + 16 <= header[1]:
        address, size = struct.unpack_from('>QQ', data, offset)
        offset += 16
        if not address and not size:
            return header[5:8], reservations
        reservations.append((address, size))
    raise ValueError('invalid FDT memory reservation table')


def audit(fit, root):
    nodes = nodes_with_status(fit, root)
    soc = nodes['/soc'][0]
    if (fit.number(soc.props['#address-cells']) != 2
            or fit.number(soc.props['#size-cells']) != 2 or soc.props.get('ranges', b'')):
        raise ValueError('requires the known identity-mapped Jupiter2 /soc layout')
    targets = []
    for index in range(4):
        address = 0xcac90000 + index * 0x400
        path = f'/soc/mailbox{index}@{address:x}'
        node, enabled = nodes[path]
        if ('spacemit,k3-mailbox' not in fit.strings(node.props['compatible'])
                or node.props['reg'] != struct.pack('>4I', 0, address, 0, 0x400)):
            raise ValueError('unexpected mailbox layout: ' + path)
        targets.append({'path': path, 'was_enabled': enabled})
    target_paths = {t['path'] for t in targets}
    handles = {}
    for path, (node, _) in nodes.items():
        prop = node.props.get('phandle', node.props.get('linux,phandle'))
        if prop:
            handle = fit.number(prop)
            if handle in handles:
                raise ValueError('duplicate DT phandle')
            handles[handle] = (path, node)
    references = []
    for path, (node, enabled) in nodes.items():
        if 'mboxes' not in node.props:
            continue
        data = node.props['mboxes']
        if len(data) % 4:
            raise ValueError('invalid mboxes cells at ' + path)
        cells = struct.unpack('>' + 'I' * (len(data) // 4), data)
        index = 0
        while index < len(cells):
            if cells[index] not in handles:
                raise ValueError('unknown mailbox provider at ' + path)
            provider_path, provider = handles[cells[index]]
            count = fit.number(provider.props['#mbox-cells'])
            if index + 1 + count > len(cells):
                raise ValueError('truncated mailbox reference at ' + path)
            if provider_path in target_paths:
                references.append({'consumer': path, 'enabled': enabled,
                                   'provider': provider_path})
                if enabled:
                    raise ValueError('enabled mailbox consumer prevents preparation: ' + path)
            index += 1 + count
    return nodes, targets, references


def prepare(source, output, report):
    if source.resolve() == output.resolve():
        raise ValueError('input and output must differ; keep the original Linux DTB')
    fit = load_fit_parser()
    data = source.read_bytes()
    root, _ = fit.parse_fdt(data)
    before, targets, references = audit(fit, root)
    executable = shutil.which('fdtput')
    if not executable:
        raise ValueError('install device-tree-compiler (fdtput required on PC)')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.jupiter2-linux-dtb-', dir=output.parent) as temp:
        staged = Path(temp) / 'linux.dtb'
        staged.write_bytes(data)
        for target in targets:
            subprocess.run([executable, '-t', 's', str(staged), target['path'], 'status', 'disabled'],
                           check=True, capture_output=True)
        result = staged.read_bytes()
        if fdt_metadata(data) != fdt_metadata(result):
            raise ValueError('DT version/boot CPU/memory reservations changed unexpectedly')
        changed, _ = fit.parse_fdt(result)
        after, _, _ = audit(fit, changed)
        if before.keys() != after.keys():
            raise ValueError('DT nodes changed unexpectedly')
        paths = {t['path'] for t in targets}
        for path, (node, _) in before.items():
            old, new = dict(node.props), dict(after[path][0].props)
            if path in paths:
                old.pop('status', None)
                if new.pop('status', None) != fit.text('disabled'):
                    raise ValueError('mailbox controller was not disabled')
            if old != new:
                raise ValueError('unexpected property change at ' + path)
        if output.exists():
            if output.read_bytes() != result:
                raise ValueError('output exists with different content; choose another filename')
        else:
            os.link(staged, output)
    record = {'scope': 'Linux mailbox0..3 DT ownership only', 'hardware_verified': False,
              'input_name': source.name, 'input_bytes': len(data),
              'input_sha256': hashlib.sha256(data).hexdigest(),
              'output_name': output.name, 'output_bytes': len(result),
              'output_sha256': hashlib.sha256(result).hexdigest(),
              'm_only_page': '0xcac90000-0xcac90fff',
              'controllers': targets, 'references': references,
              'only_changes': 'status=disabled on the four listed controllers'}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(record, indent=2) + '\n')
    print(output)
    print(f'Limited DT inspection passed; actual SM/Linux/Enclave execution unverified. Report: {report}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = args.report or args.output.with_suffix(args.output.suffix + '.json')
    try:
        if report.resolve() in (args.input.resolve(), args.output.resolve()):
            raise ValueError('report must not overwrite an input/output DTB')
        if report.exists() and any(p.exists() and os.path.samefile(report, p)
                                   for p in (args.input, args.output)):
            raise ValueError('report must not share the input/output DTB inode')
        prepare(args.input, args.output, report)
    except (ValueError, KeyError, OSError, UnicodeError, struct.error,
            subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
