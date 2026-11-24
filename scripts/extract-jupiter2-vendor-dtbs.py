#!/usr/bin/env python3
"""Extract the board and RCPU DTBs from the repository's Jupiter2 vendor FITs."""

import json
import runpy
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
HARDWARE = SCRIPTS.parent / 'hardware/jupiter2'
VENDOR = HARDWARE / 'vendor'


def main():
    fit = SimpleNamespace(**runpy.run_path(str(SCRIPTS / 'build-jupiter2-ram-boot-image.py')))
    unpack = runpy.run_path(str(SCRIPTS / 'build-jupiter2-reference-ram-boot.py'))['fit_payload']

    profile = json.loads((HARDWARE / 'vendor-fit.json').read_text())
    board_name = profile['board']
    uboot_config = profile['uboot_configuration']
    esos_config = profile['esos_configuration']
    uboot, blob, total = fit.read_fit(VENDOR / 'u-boot.itb')
    config = uboot.children['configurations'].children[uboot_config]
    if fit.string(config, 'description') != board_name:
        raise ValueError(f'U-Boot {uboot_config} does not describe {board_name}')
    name = fit.string(config, 'fdt')
    board = uboot.children['images'].children[name]
    if fit.string(board, 'type') != 'flat_dt':
        raise ValueError(f'U-Boot image {name} is not a flat device tree')
    outputs = {f'u-boot-{board_name}.dtb': unpack(fit, board, blob, total)}

    esos, blob, total = fit.read_fit(VENDOR / 'esos.itb')
    config = esos.children['configurations'].children[esos_config]
    loadables = fit.strings(config.props['loadables'])
    for name in profile['esos_dtb_images']:
        if name not in loadables:
            raise ValueError(f'ESOS {esos_config} is missing {name}')
        node = esos.children['images'].children[name]
        outputs[f'esos-{name}.dtb'] = unpack(fit, node, blob, total)

    for name in outputs:
        if Path(name).name != name:
            raise ValueError(f'invalid DTB output name: {name}')
    for payload in outputs.values():
        fit.parse_fdt(payload)
    for name, payload in outputs.items():
        path = VENDOR / name
        path.write_bytes(payload)
        print(path)


if __name__ == '__main__':
    try:
        main()
    except (OSError, KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
