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

`docs/milkv-jupiter2-stack-install.md`に従い新Linux単独確認、firmware更新、trial起動を行った後：

```bash
sudo bash tools/run-hello.sh
```

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

詳しくは[同梱手順書の第5章](docs/milkv-jupiter2-stack-install.md#5-容量確認とインストールイメージ作成)を参照。

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
