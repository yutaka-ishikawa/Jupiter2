#!/usr/bin/env python3
"""Extract the board and RCPU DTBs from the repository's Jupiter2 vendor FITs."""

import runpy
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parent
VENDOR = SCRIPTS.parent / 'hardware/jupiter2/vendor'
RCPU_IMAGES = ('rcpu0-dtb-pico-itx', 'rcpu1-dtb-pico-itx')


def main():
    fit = SimpleNamespace(**runpy.run_path(str(SCRIPTS / 'build-jupiter2-ram-boot-image.py')))
    unpack = runpy.run_path(str(SCRIPTS / 'build-jupiter2-reference-ram-boot.py'))['fit_payload']

    uboot, blob, total = fit.read_fit(VENDOR / 'u-boot.itb')
    config = uboot.children['configurations'].children['conf_11']
    if fit.string(config, 'description') != 'k3-pico-itx':
        raise ValueError('U-Boot conf_11 does not describe k3-pico-itx')
    name = fit.string(config, 'fdt')
    board = uboot.children['images'].children[name]
    if fit.string(board, 'type') != 'flat_dt':
        raise ValueError(f'U-Boot image {name} is not a flat device tree')
    outputs = {'u-boot-k3-pico-itx.dtb': unpack(fit, board, blob, total)}

    esos, blob, total = fit.read_fit(VENDOR / 'esos.itb')
    config = esos.children['configurations'].children['conf_dual']
    loadables = fit.strings(config.props['loadables'])
    for name in RCPU_IMAGES:
        if name not in loadables:
            raise ValueError(f'ESOS conf_dual is missing {name}')
        node = esos.children['images'].children[name]
        outputs[f'esos-{name}.dtb'] = unpack(fit, node, blob, total)

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
