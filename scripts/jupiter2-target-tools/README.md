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

install-linux.shは新releaseのLinux/modules/appsだけを配置する。initramfs、boot entry、
firmware更新は自動実行しない。容量や既存releaseで停止したら原因を解決してから進む。
配置途中のI/O失敗に対する全体rollbackはなく、再実行前に部分配置を確認する。

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
