# Milk-V Jupiter2で販売元Linuxを一時起動する

Keystone・OP-TEE同梱のRAM起動イメージでU-Bootを起動し、UFS上の販売元Linux・initrd・DTBを使います。
設定はU-BootのRAM上で行うため、`saveenv` は不要です。

## 起動の前提条件

- 開発PCに、同じビルドで生成した `FSBL.bin` と Keystone・OP-TEE同梱の
  `ram-boot-keystone.itb` を用意します。統合FITのU-Bootで `scsi`、`unzip`、`booti` が使えることが前提です。
- UFSのブートパーティション（この例ではU-Bootの `scsi 0:2`）の直下に、
  **変更前の販売元の `env_k3.txt` を `env_k3.txt.org` として保存済み**であることが前提です。
  このパーティションをLinuxで `/boot` にマウントしている場合の保存先は `/boot/env_k3.txt.org` です。
  まだ保存していなければ、販売元の `env_k3.txt` を変更する前にコピーしてください。
  すでに変更済みなら、保存してある変更前のバックアップから配置します。
- 同じブートパーティションに、設定が指す販売元のカーネル・initrd・実機モデル用DTBが残っていることを確認します。
  この例では `/vmlinuz-6.18.3-generic`、`/initrd.img-6.18.3-generic`、
  `/spacemit/6.18.3-generic/k3-pico-itx.dtb` を使います。
- 販売元Linuxのルートファイルシステムと、そのカーネルに対応するモジュール一式が残っていることを確認します。
  後述の `root=PARTUUID` は、そのルートパーティションの値を使います。

## USBからFSBLと統合FITをRAMへ転送する

以下のUSB転送とU-Bootの起動は実機で確認済みです。
[RAM起動ガイド](jupiter2-ram-boot-guide.md)に従ってUARTとUSBを接続し、
電源を切った状態からFDLボタンを押して電源を入れます。

開発PCで、同じビルドの `FSBL.bin` と `ram-boot-keystone.itb` があるディレクトリへ移動します。
まずROMのfastboot機器を確認し、FSBLを転送して実行します。

```bash
IMAGES=.
FSBL="$IMAGES/FSBL.bin"
UBOOT="$IMAGES/ram-boot-keystone.itb"
sudo fastboot devices
sudo fastboot stage "$FSBL"
sudo fastboot continue
```

UARTでDDR初期化の完了を確認し、USBがSPLのfastboot機器として再認識されるまで待ちます。
以下のシリアル番号は実機で確認した値です。別の個体では `fastboot devices` の表示に合わせます。
`max-download-size` にFITが収まることを確認してから `stage` に進みます。

```bash
sudo fastboot devices
sudo fastboot -s HW4MPK3321280144 getvar max-download-size
sudo fastboot -s HW4MPK3321280144 getvar version
sudo fastboot -s HW4MPK3321280144 stage "$UBOOT"
sudo fastboot -s HW4MPK3321280144 continue
```

UARTでU-Bootの自動起動を止め、`=>` プロンプトに入ります。

## 販売元の設定を取り込む

U-Bootの `=>` で入力します。各 `load` が成功してから次の行に進みます。

```text
scsi scan
ls scsi 0:2 /
setenv kernel_addr_r 0x140000000
load scsi 0:2 ${kernel_addr_r} /env_k3.txt.org
env import -t ${kernel_addr_r} ${filesize}
printenv knl_name ramdisk_name dtb_dir ramdisk_addr
ls scsi 0:2 /${dtb_dir}/
```

実機で使った設定は `knl_name=vmlinuz-6.18.3-generic`、
`ramdisk_name=initrd.img-6.18.3-generic`、`dtb_dir=spacemit/6.18.3-generic`、
`ramdisk_addr=0x130000000` です。DTB一覧で販売元の
`k3-pico-itx.dtb` を確認します。`bootcmd` は手動起動では不要です。

## カーネルをRAMで展開して起動する

以下のアドレスは今回のRAM起動構成の値です。別の構成で使う場合は、
展開先 `0x148000000` から128 MiBの範囲が使用可能なRAMで、予約領域と重ならないことを確認します。

```text
setenv fdtfile k3-pico-itx.dtb
setenv fdt_addr_r 0x138000000
load scsi 0:2 ${kernel_addr_r} /${knl_name}
unzip ${kernel_addr_r} 0x148000000 0x08000000
md.b 0x148000030 10
```

`unzip` が成功し、ダンプに `52 49 53 43 56`（`RISCV`）が出ることを確認します。
次にinitrdとDTBを読み込みます。`initrd_size` はinitrdを読み込んだ直後に保存します。

```text
load scsi 0:2 ${ramdisk_addr} /${ramdisk_name}
setenv initrd_size ${filesize}
load scsi 0:2 ${fdt_addr_r} /${dtb_dir}/${fdtfile}
fdt addr ${fdt_addr_r}
fdt header
```

`fdt header` に `magic: 0xd00dfeed` が表示されたら、起動します。
以下の `root=PARTUUID` は今回の実機の値なので、別のルートパーティションを使う場合は置き換えます。

```text
setenv bootargs console=ttyS0,115200 earlycon=sbi root=PARTUUID=73708e51-d3a9-4b6f-ab55-894cd1d8b4a0 rootwait rw loglevel=8
booti 0x148000000 ${ramdisk_addr}:${initrd_size} ${fdt_addr_r}
```

`Starting kernel ...` が出ればLinuxへの引き渡しまで進んでいます。
Linuxにログインしたら `uname -r` が `6.18.3-generic` を返すことを確認します。
採取済みのログでは、カーネルの展開とDTBヘッダーの認識まで確認できています。
