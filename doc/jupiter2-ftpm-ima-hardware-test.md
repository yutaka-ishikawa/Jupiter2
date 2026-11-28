# Jupiter2実機でIMAとfTPMの連携を確認する

Pico-ITXをUSB RAM起動し、IMAのファイル測定がfTPMのSHA-256バンクのPCR 10を
更新することを確認する。16 hartのJupiter2 QEMUでは、IMA初期化前にfTPMを登録すると
測定ログから計算した期待値にPCR 10が更新され、初期化後に登録するとPCR 10は変化しなかった。
この手順の実機での結果は未検証。[QEMUの試験結果](jupiter2-ftpm-ta-test.md#ftpmとlinux-imaのqemu試験)

試験用カーネルは、通常の `/init` より前に `/ima-ftpm-prepare` を呼ぶ。
このヘルパーが `tee-supplicant` を起動し、fTPMドライバーをロードする。
fTPMが登録された状態でIMAが初期化され、その後に試験用 `/init` が測定とPCRの照合に必要な
情報をUARTへ出力して電源断する。試験はinitramfs内で完結する。

## 1. 開発PCで試験用Imageとinitramfsを作る

Jupiter2リポジトリのルートで実行する。試験用カーネルと同じビルドのモジュールを組み合わせる。

```bash
make ftpm-ima JOBS=20
```

`make ftpm-ima` で試験用カーネル、fTPM TA、静的リンクされたRV64版の
`tee-supplicant` と試験ヘルパーが生成される。次のコマンドはQEMUランナーと
同じ内容のinitramfsを作る。QEMU試験で生成した `.build-k3/ftpm-ima/init.cpio` を再利用する場合は、
同じ実行で使用したImageと `probe` も揃える。
[QEMUランナー](../scripts/tests/jupiter2-ftpm-ima-qemu.sh)

```bash
(
    set -eu
    LINUX_OUT="$PWD/.build-k3/ftpm-ima-linux"
    FTPM_OUT="$PWD/.build-k3/ftpm-test"
    OUT="$PWD/.build-k3/ftpm-ima-hardware"
    UUID=bc50d971-d4c9-42c4-82cb-343fb7f37896
    mkdir -p "$OUT"
    printf 'Jupiter2 fTPM IMA test probe\n' > "$OUT/probe"

    cat > "$OUT/init.list" <<LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
dir /lib 0755 0 0
dir /lib/optee_armtz 0755 0 0
dir /var 0755 0 0
dir /var/lib 0755 0 0
dir /var/lib/tee 0700 0 0
file /lib/optee_armtz/$UUID.ta $FTPM_OUT/ta/$UUID.ta 0644 0 0
file /tee-supplicant $FTPM_OUT/client/tee-supplicant/tee-supplicant 0755 0 0
file /init $LINUX_OUT/ftpm-ima-init 0755 0 0
file /tpm_ftpm_tee.ko $LINUX_OUT/drivers/char/tpm/tpm_ftpm_tee.ko 0644 0 0
dir /sys 0755 0 0
dir /sys/kernel 0755 0 0
dir /sys/kernel/security 0755 0 0
slink /ima-ftpm-prepare /init 0755 0 0
file /ima-probe $OUT/probe 0644 0 0
LIST

    "$LINUX_OUT/usr/gen_init_cpio" "$OUT/init.list" > "$OUT/init-ftpm-ima.cpio"
    cp -- "$LINUX_OUT/arch/riscv/boot/Image" "$OUT/Image-ftpm-ima"
    (cd "$OUT" && sha256sum Image-ftpm-ima init-ftpm-ima.cpio)
)
```

`Image-ftpm-ima` と `init-ftpm-ima.cpio` を実機の起動パーティションのルートへコピーする。
`probe` はUARTログの検証に使うので開発PCに残す。

## 2. Jupiter2を一時起動する

基本動作を確認した実機用のKeystone・OP-TEE同梱FITをUSB RAM起動し、UARTでU-Bootの
プロンプトに入る。実機用 `k3-pico-itx-keystone-optee.dtb` は同じFITに対応し、
`/tpm` の `compatible` が `microsoft,ftpm` のものを使う。
FIT内のCoreには、試験用fTPM TAを検証できる署名鍵設定が必要。
eFuse未書き込み機での既存の基本試験は、開発用HUKを許可した評価用Coreを使用した。
[USB RAM起動と実機用DTBの読み込み](jupiter2-ram-boot-guide.md#coexistence-linux-boot) ·
[実機でのfTPM基本動作結果](milkv-jupiter2-stack-install.md#pico-itx-ftpm-pass)

UARTの記録を開始する。以下は起動パーティションが `scsi 0:2` の例。
`scsi scan` 後に実機のパーティションとDTBの配置先を確認して読み替える。
各 `load` の成功を確認してから次へ進み、initramfsの読み込み直後にサイズを保存する。

```text
scsi scan
setenv kernel_addr_r 0x140000000
setenv ramdisk_addr 0x130000000
setenv fdt_addr_r 0x138000000
setenv dtb_dir spacemit/6.18.3-generic
load scsi 0:2 ${kernel_addr_r} /Image-ftpm-ima
load scsi 0:2 ${ramdisk_addr} /init-ftpm-ima.cpio
setenv initrd_size ${filesize}
load scsi 0:2 ${fdt_addr_r} /${dtb_dir}/k3-pico-itx-keystone-optee.dtb
fdt addr ${fdt_addr_r}
fdt print /firmware/optee
fdt print /tpm
```

`/firmware/optee` に `linaro,optee-tz` と `mboxes`、`/tpm` に
`microsoft,ftpm` が表示されたら、今回の起動引数で実行する。
`ima_test_ftpm=1` が早期起動ヘルパーを有効にする。`setenv` の変更は今回の起動に使う。

```text
setenv bootargs console=ttyS0,115200 earlycon=sbi keep_bootcon printk.devkmsg=on loglevel=8 ima_test_ftpm=1 rdinit=/init ima_hash=sha256
booti ${kernel_addr_r} ${ramdisk_addr}:${initrd_size} ${fdt_addr_r}
```

## 3. UARTログで判定する

- `QEMU fTPM preparation status=0` が出れば、IMA初期化前のfTPM登録が完了した。
  `QEMU` は試験パッチの固定文言で、実機でも同じ表示になる。
- `IMA_MEASUREMENT 10 ... /ima-probe` が出て、`IMA_PCR_BEFORE` と
  `IMA_PCR_AFTER` が異なることを確認する。
- `IMA_GUEST_RESULT=0` と電源断を確認し、開発PCでPCR 10の値を照合する。

ログを `pico-itx-ima-uart.log` に保存した例を示す。QEMUで作ったinitramfsを再利用した場合は、
そのinitramfsと一緒に作成した `probe` に読み替える。

```bash
python3 scripts/tests/jupiter2-ftpm-ima-verify.py early \
    pico-itx-ima-uart.log .build-k3/ftpm-ima-hardware/probe
```

照合は試験ファイルのダイジェストと
`SHA256(更新前のPCR 10 || IMAのテンプレートダイジェスト)` を検証する。
`PASS: IMA SHA-256 extension matches fTPM PCR 10` が合格。
早期登録が失敗した場合は、UARTで `IMA prep:`、`ftpm-tee`、`HUK` と
`fTPM preparation status=` の前後を確認する。
通常のBianbuに戻すときは、次の起動で従来のImage・initrd・起動引数を選ぶ。
通常のBianbu起動への早期登録の組み込みは、この試験の後に行う。
