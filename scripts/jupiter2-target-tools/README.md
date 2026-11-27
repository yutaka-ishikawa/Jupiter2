# Milk-V Jupiter2 配布ディレクトリ

このbundleには実機へ配置する成果物、検証ツールと手順書をまとめている。
Linuxとアプリを配置する場合は、`kernelrelease.txt`を含む通常bundleを使う。

## 実機での順序

1. 転送したアーカイブと展開したbundleを確認する。`bash tools/preflight.sh`で、内容のハッシュと実機のNOR容量・実行環境を確認できる。[転送と事前検査](docs/milkv-jupiter2-stack-install.md#4-bundleの転送と事前検査)
2. 使用中の起動設定、bootfs、旧Linuxを記録・バックアップする。`env_k3.txt`を使う構成では日付付きのコピーも保存する。[現状記録とバックアップ](docs/milkv-jupiter2-stack-install.md#5-実機の現状記録とバックアップ)
3. `sudo bash tools/install-linux.sh`でImage、モジュール、ドライバ、hello二種を配置し、対応するinitrdとLinux用DTBを準備する。上書きとバックアップ保存はスクリプトが配置前に確認する。[Linuxの配置とinitrd生成](docs/milkv-jupiter2-stack-install.md#6-新linuxとアプリを追加配置する)
4. 既存のOpenSBIで新Linuxを一時起動し、元の起動設定を保持した状態で確認する。[試験用Linuxの起動](docs/milkv-jupiter2-stack-install.md#7-試験用boot-entryを追加する)
5. 使用するファームウェアで起動し、対応するLinuxからKeystone・OP-TEEを試験する。NORへの書き込みは専用手順に従う。[ブートイメージの導入](docs/milkv-jupiter2-stack-install.md#8-ブートイメージの導入) · [実機での試験](docs/milkv-jupiter2-stack-install.md#9-実機での基本確認)

復旧は、Linuxの起動設定とブートイメージのどちらを変更したか確認してから行う。
[復旧手順](docs/milkv-jupiter2-stack-install.md#10-復旧と正式採用)

FITのみのbundleでは、`bash tools/verify.sh`で同梱ファイルを検証し、
`python3 tools/check-capacity.py --image firmware/fw_dynamic.itb`で区画容量を確認する。
[OpenSBIの更新・復旧手順](docs/milkv-jupiter2-opensbi-replacement.md)

## bundle内の記録ファイル

- `source-commit.txt`、`source-local.patch`、`source-untracked.txt`。作成時のコミット、追跡済み差分、未追跡ファイルのパス。
- `capacity.json`、`fit-inspection.txt`。作成時の容量検査とFIT情報。
- `kernelrelease.txt`。通常bundleのカーネルリリース。
- `SHA256SUMS`。展開後の照合用ハッシュ。

## 実機OSの依存

実機用のPython 3.11以上、Bash、coreutils、kmod、tar、gzipを使う。
initrdの作成には使用中のOSに合ったツールを用意する。Bianbuの例では
`initramfs-tools`、LinuxからのNOR更新には`mtd-utils`を使う。
[実機側の事前検査](docs/milkv-jupiter2-stack-install.md#4-bundleの転送と事前検査)
