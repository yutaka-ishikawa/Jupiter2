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

## 2段階の起動確認

1. **新Linux＋既存OpenSBI**：initramfs生成とkernel選択変更を行い、再起動して新kernelの通常動作を確認する。この段階ではKeystone driverをロードせず、helloも実行しない。
2. **同じ新Linux＋新OpenSBI／SM**：第1段階の成功後にOpenSBIだけ更新し、同じkernelの起動を確認する。その後、以下のhelloを実行する。

新kernelを選ぶ設定は第1段階の成功後も維持する。第2段階へ進むために旧kernelへ戻す必要はない。

手順の詳細は[同梱手順書](docs/milkv-jupiter2-stack-install.md)の第6〜9章を参照。
失敗した場合は[第10章のrollback](docs/milkv-jupiter2-stack-install.md#10-復旧と正式採用)に従う。
第1段階では元のLinux起動設定へ戻し、第2段階ではまず元OpenSBIへ戻す。
Linuxが起動しない場合の復旧用Linux／FDLの手順も同章に記載している。

第2段階でSMと新kernelの起動を確認した後：

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
