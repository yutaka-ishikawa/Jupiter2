# Jupiter2 QEMUの使い方

リポジトリのルートで `bash scripts/run-k3.sh` を実行します。
各構成の成果物は [ビルド・インストール・試験手順](qemu-build-install-test.md) に従って用意します。
以下はディスク上のrootfsからLinuxを起動し、端末から操作する例です。
既存の同居・OP-TEE単独の検証手順は専用initramfsを使います。ここに掲載する
OP-TEE入り2構成のディスク起動例は、この文書の作成時点ではQEMUで未検証です。

## 1. KeystoneとOP-TEEを同梱する

Keystone SM入りのOpenSBI、Keystone用rootfs、OP-TEE Coreを使います。
同居用 `boot.dtb` は `make optee-coexist-test` で生成します。

```bash
WORK="$PWD/.build-k3/optee-coexist"

bash scripts/run-k3.sh \
  --image keystone --prefix "$PWD/install/keystone" \
  --dtb "$WORK/boot.dtb" --optee-elf "$WORK/out/core/tee.elf" \
  --smp 16 --memory 2G --sstc on --wtm-rng on
```

外部TAを実行する場合は、対応するTAと `tee-supplicant` をゲストのrootfsに用意します。

## 2. Keystoneのみ

Keystone SM入りOpenSBIとKeystone用rootfsで起動します。
標準設定での短縮形は `make run` です。Sstcを明示する場合は次のように起動します。

```bash
bash scripts/run-k3.sh \
  --image keystone --prefix "$PWD/install/keystone" \
  --smp 16 --memory 2G --sstc on
```

## 3. OP-TEEのみ

`install/optee/` に配置したKeystone SMなしのK3 OpenSBIとLinuxを使います。
Bianbuのrootfsがまだない場合は初回に作成します。

```bash
bash scripts/build-install-k3.sh --only rootfs --prefix "$PWD/install/optee"
```

単独構成の手順で生成した `.build-k3/optee-only-test/boot.dtb` とOP-TEE Coreを指定します。

```bash
WORK="$PWD/.build-k3/optee-coexist"
OPTEE_PREFIX="$PWD/install/optee"

bash scripts/run-k3.sh \
  --image bianbu --prefix "$OPTEE_PREFIX" \
  --bios "$OPTEE_PREFIX/firmware/k3/fw_dynamic.bin" \
  --dtb "$PWD/.build-k3/optee-only-test/boot.dtb" \
  --optee-elf "$WORK/out/core/tee.elf" \
  --smp 16 --memory 2G --sstc on --wtm-rng on
```

`--image bianbu` はrootfsの既定名とLinuxの既定起動引数を選びます。
Keystone SMの有無はOpenSBIのビルド設定で決まります。

## 起動コマンドのオプション

### 起動ファイルとゲストディスク

| オプション | 説明 |
| --- | --- |
| `--image keystone\|bianbu` | プロファイルを選択。既定は `keystone` |
| `--prefix DIR` | インストール先。既定は `install/<プロファイル>/` |
| `--qemu FILE` | QEMU実行ファイル。既定はPREFIX内の `bin/qemu-system-riscv64` |
| `--bios FILE` | OpenSBIを指定。既定はPREFIX内の `firmware/k3/fw_dynamic.bin`。乱数・暗号プロファイル指定時は対応するイメージを選択できる |
| `--kernel FILE` | Linuxカーネル。既定はPREFIX内の `boot/k3/Image` |
| `--dtb FILE` | QEMUに渡す起動DTB。OP-TEE入り構成では明示する |
| `--optee-elf FILE` | OP-TEE CoreのリトルエンディアンELF64をメモリへロードする。`--dtb` が必須 |
| `--rootfs FILE` | ゲストディスク。既定はPREFIX内の `rootfs/keystone-rootfs.img` または `rootfs/bianbu-rootfs.img` |
| `--rootfs-format raw\|qcow2` | ゲストディスクの形式。既定は `raw` |
| `--append TEXT` | Linux起動引数全体を置き換える。ディスク起動に必要な `root=/dev/vda rw rootwait` なども指定する |

既定の起動引数は `root=/dev/vda rw rootwait console=ttyS0,115200 earlycon=sbi init=/bin/bash loglevel=7` です。
Keystoneプロファイルでは `cma=512M@4G-16G` が加わります。

### CPU、PMP、乱数

| オプション | 説明 |
| --- | --- |
| `--smp N`、`--memory SIZE` | hart数とメモリ容量。既定は16 hart、2 GiB。OP-TEE用DTBと整合する値を使う |
| `--pmp-profile uniform16\|mixed` | PMP構成を指定。既定は `uniform16` |
| `--sstc on\|off` | CPUのSstcを指定。未指定時はCPUモデルの既定値 |
| `--wtm-rng on\|off` | WTMと未書き込みGEU eFuseのQEMUモデルを切り替える |
| `--rng auto\|zkr\|jupiter2\|counter` | Keystoneの乱数構成を選択。明示した `--bios` があれば、そのイメージが優先される |
| `--crypto unavailable\|qemu-dev` | 通常構成または開発用暗号ファームウェアを選択。`qemu-dev` と併用できる `--rng` は `auto` |
| `--zkr on\|off` | Zkr拡張を明示的に切り替える |
| `--wtm-rng-fault none\|not-ready\|zero` | QEMU上のWTM障害試験用。既定は `none` |

### 端末、共有、デバッグ

| オプション | 説明 |
| --- | --- |
| `--hostfs DIR` | 9pで共有するホスト側ディレクトリ。既定はリポジトリルート、マウントタグは `hostshare` |
| `--console` | シリアルとQEMUモニターを端末で多重化する。`Ctrl-A` の後に `C` で切り替える |
| `--monitor`、`--monitor-port N` | TCPモニターをループバックで有効にする。既定ポートは4444 |
| `--gdb`、`--gdb-port N` | ゲストを起動時に停止し、ループバックでGDB接続を待つ。既定ポートは1234 |
| `--help`、`-h` | オプション一覧を表示する |

オプションの実装と既定値は [起動スクリプト](../scripts/run-k3.sh) と
[QEMU設定](../hardware/jupiter2/qemu.conf) を参照してください。
