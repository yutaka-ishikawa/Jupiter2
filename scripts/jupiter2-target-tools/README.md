# Milk-V Jupiter2 配布ディレクトリ

このbundleを丸ごと実機へ転送する。実機側にGit checkoutやクロスコンパイラーは不要。
firmware、Linux、全kernel modules、Keystone driver、hello二種、tools、docsをまとめている。
firmware-only版にはLinux/modules/appsはなく、OS配置・hello実行は使えない。

## 実機での順序

展開先bundle内で実行する。OS配置・実行は段階別に行う。

```bash
bash tools/verify.sh
bash tools/preflight.sh
sudo bash tools/install-linux.sh
```

## install-linux.shが配置するファイル

`<release>`は`kernelrelease.txt`の値を表す。

| bundle内 | 実機への配置先 |
| --- | --- |
| `linux/Image` | `/boot/Image-<release>-keystone` |
| `linux/config` | `/boot/config-<release>-keystone` |
| `modules/<release>/`（Keystone driverを含む） | `/lib/modules/<release>/` |
| `apps/hello.ke`、`apps/hello-native.ke` | `/opt/keystone/<release>/` |

配置後に`depmod -a <release>`を実行する。
**新Linuxは起動せず、現在のkernelも次回の起動先も変更しない。**
initramfs生成は同梱手順書の第6章、起動kernelの選択は第7章、OpenSBI＋SM更新は第8章を参照する。
`env_k3.txt`を使う場合の変更箇所も第7章に記載している。
DTB配置、firmware書込み、driverロード、再起動は行わない。
配置途中の失敗ではコピー済みファイルを自動削除しないため、再実行前に上表の配置先を確認する。

## 配置後にinitrdを作る

**install-linux.shはinitrdを生成しない。**
新kernelのreleaseはbundle内の`kernelrelease.txt`と配置済みmodulesで確認する。
今回の`Image-6.18.3-keystone`に対応するreleaseは`6.18.3`であり、
ファイル名の末尾`-keystone`を`update-initramfs -k`へ付けない。

同梱手順書の[第6章](docs/milkv-jupiter2-stack-install.md#6-新linuxとアプリを追加配置する)に従い、
実機上でmodulesと標準名のconfigを準備してから：

```bash
sudo update-initramfs -c -k 6.18.3
ls -lh /boot/initrd.img-6.18.3
```

既に作成済みの同releaseを更新する場合は`-u`を使う。
生成が成功した後、UARTのU-Bootで今回の値を指定する。

```text
setenv knl_name Image-6.18.3-keystone
setenv ramdisk_name initrd.img-6.18.3
setenv dtb_dir spacemit/6.18.3-generic
printenv knl_name ramdisk_name dtb_dir
```

DTBは既存の実機用directoryを継続利用する例で、新kernelとの適合を確認する。
`env_k3.txt`の編集・`saveenv`はこの試験前に行わない。
別releaseの場合は、同梱手順書第6・7章の照合方法で実際のファイル名に合わせる。

## 2段階の起動確認

1. **新Linux＋既存OpenSBI**：kernel配置とinitramfs生成後も`env_k3.txt`は変更しない。UARTでU-Bootを止め、RAM上の`knl_name`・`ramdisk_name`・`dtb_dir`を新kernel用にして起動する。`saveenv`は使わない。正常動作確認後に`env_k3.txt`へ同じ値を設定し、通常再起動でも新kernelが選ばれることを確認する。この段階ではKeystone driverをロードせず、helloも実行しない。
2. **同じ新Linux＋新OpenSBI／SM**：第1段階の成功後にOpenSBIだけ更新し、同じkernelの起動を確認する。その後、以下のhelloを実行する。

新kernelを選ぶ設定は第1段階の成功後も維持する。第2段階へ進むために旧kernelへ戻す必要はない。

手順の詳細は[同梱手順書](docs/milkv-jupiter2-stack-install.md)の第6〜9章を参照。
失敗した場合は[第10章のrollback](docs/milkv-jupiter2-stack-install.md#10-復旧と正式採用)に従う。
第1段階のRAM試験で失敗した場合は、再起動すれば未変更の`env_k3.txt`から旧kernelが選ばれる。
永続化後の失敗はUARTから旧kernelを一時起動して元のファイルを復元する。
第2段階ではまず元OpenSBIへ戻す。
Linuxが起動しない場合の復旧用Linux／FDLの手順も同章に記載している。

第2段階でSMと新kernelの起動を確認した後：

```bash
sudo bash tools/run-hello.sh
```

## bundleからOpenSBIとSMを書き込む

第1段階の新kernel起動確認後、実機Linux上で
[同梱手順書の第8章](docs/milkv-jupiter2-stack-install.md#8-opensbiとsmを置換する)を実行する。
今回のNOR `mtd5`に対して、bundle内の`firmware/fw_dynamic.itb`を`flashcp`で書き込む。
同章に容量・checksum・backupの検査、実際の書込み、読戻し照合、再起動までのコマンドを記載している。
`install-linux.sh`はfirmwareを書き込まない。
失敗時の元OpenSBI復元は同梱手順書の第10章を参照する。

容量の再確認だけなら：

```bash
python3 tools/check-capacity.py --image firmware/fw_dynamic.itb --mtd mtd5
```

firmware-only版はverify.shとcheck-capacity.pyを使い、firmware置換は同梱docsを参照する。
preflight.shはOS導入用の条件も検査するためfirmware-only版の基本操作には不要。

## bundle内の記録ファイル

これらはtarに含まれる説明・検証用ファイルで、install-linux.shの配置対象ではない。

- `source-commit.txt`：作成時checkoutのcommit ID。
- `source-local.patch`：作成時checkoutの追跡済みファイルとHEADとの差分。
- `source-untracked.txt`：作成時checkoutのGit未追跡ファイルのパス一覧。ファイル本体やtar収録一覧ではない。
- `capacity.json`、`fit-inspection.txt`：作成時の容量検査結果とFIT情報。
- `kernelrelease.txt`：同梱kernelのrelease。
- `SHA256SUMS`：bundle内の通常ファイルの検査用hash一覧。

詳しくは[同梱手順書の第4章](docs/milkv-jupiter2-stack-install.md#4-容量確認とインストールイメージ作成)を参照。

## OS標準ツールの依存

Python 3.11以上、Bash、coreutils、kmodが必要。Debian/Bianbu系では通常
`python3 bash coreutils kmod`に対応する。展開にはtar/gzipが必要。
initramfs-tools、GRUB/extlinux等は使用中のOSの方式に従う。
NOR更新をLinux上で行う場合は、その実機向けmtd-utils（flashcp等）をOSから導入する。

これらのOS標準バイナリーを開発PCからコピーしない。x86_64ホスト用バイナリーは
RISC-V実機では動かず、実機OSのlibcとも整合しないため、本bundleには含めない。
preflight.shが主要コマンドの有無を確認する。オフライン導入なら対象OSと同じ
release/architectureの依存パッケージを別途用意する。

docs内の文書リンクは同梱資料で参照できる。`../opensbi/`等のソースコードへのリンクは
ソースリポジトリを参照する。SHA256SUMSは転送の破損検査であり署名認証ではない。
このbundleの作成成功は実機起動や隔離の保証ではない。
