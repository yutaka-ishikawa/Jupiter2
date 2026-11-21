# RAM起動用ホスト回帰試験

ここに置くのは開発PCで実行するテストスクリプト。実機へ送るコードではない。
それぞれの先頭コメントにも目的と検証範囲を記載している。

| スクリプト | 目的 | 実際に使うツール |
| --- | --- | --- |
| test_fit_packaging.py | FIT生成、ハッシュ、全ESOS loadables、LZO展開後の配置、不正入力の拒否 | dtc/mkimage/dumpimage/lzop |
| test_elf_rpmi_contract.py | ELF entryからDTへの反映、有効RPMIサーバーの選択とAP側DTの整合 | RISC-V対応clang/ld.lld、dtc |
| test_host_operations.py | 操作ツールのchecksum/dry-run、UART起動コマンドの生成・構文、同梱配置 | 実FITツール、bash -n、sha256sum |
| test_linux_dtb_preparation.py | Linux DTBのmailbox0..3のみ変更、元DTBと他ノードの保持、有効利用者がいる場合の拒否 | dtc/fdtput |
| run-host-tests.sh | 上記を必要ツール確認後にまとめて実行 | 上記すべて |

```bash
# publicリポジトリのルート、開発PCで実行
bash scripts/tests/jupiter2-ram-boot/run-host-tests.sh
```

Ubuntu/Debianの追加テスト依存例は`sudo apt-get install clang lld`。
dtc/u-boot-tools/lzop等の通常依存はRAM起動ガイドを参照する。
個別のPython試験は依存不足時にskipを表示する。完全なホスト検査ではまとめ実行を使用する。

形式試験用FSBL/ESOS/ELFは実機へ転送しない。fastbootは実行せず、UART接続もしない。
CPU/SBI/PMPを模擬しない。合格は実機・QEMU guest・Linux起動の合格を意味しない。
実機に転送する運用ツールはscripts/run-jupiter2-ram-boot.pyで、ここには置かない。
実機で確認する項目と実績はdoc/jupiter2-ram-boot-guide.mdおよび詳細テスト文書に記載する。


## 実QEMUのPMP設定確認（任意）

```bash
python3 scripts/tests/jupiter2-ram-boot/check_qemu_pmp_profile.py \
  --qemu install/keystone/bin/qemu-system-riscv64
```

更新したQEMUを実際に起動し、QMPで全CPUの個数・粒度を読み取る。
一律16個/16バイトと混在16・32個/4 KiBの両方を検査する。
停止状態のCPU設定確認であり、guestのOpenSBI/SM実行やEnclave隔離のPASSではない。
依存するQEMUがないホストでも既存の梱包試験を実行できるよう、run-host-tests.shには含めない。


## 実OpenSBI/SMとHSMの全Hart起動試験

```bash
python3 scripts/tests/jupiter2-ram-boot/run_pmp_hsm_smoke.py \
  --qemu install/keystone/bin/qemu-system-riscv64 \
  --firmware .build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic.bin \
  --output work/ksb071-pmp-hsm-smoke
```

実clang/ld.lldでpmp-hsm-smoke.SをS-mode用ELFへビルドし、実OpenSBI/SMへ渡す。
SBI HSMで各secondaryを順番に起動し、全16 HartのreadbackとS-mode到達を検査する。
起動Hartは0固定と仮定せず、QEMU/OpenSBIが選んだ起動Hart以外を開始する。
これはLinux/Enclave試験ではない。LLVM、更新QEMU、boot trace付きSM統合firmwareが必要。
outputは新しいディレクトリを指定し、失敗ログも保持する。


## 実Linuxでのhello二種・OCALL回帰試験

- linux-sample-init.sh：guestの/init。実driverをロードし、提供sampleをLinux CPU3/8に固定して実行する。開発PCの通常shellでは実行しない。
- run_linux_sample_regression.py：開発PCから実system QEMUを起動し、両PMP構成のUART出力と終了コードを判定する。比較対象の旧firmwareがあれば、旧版の終了139を期待する負の回帰試験も行う。
- linux-sample-kernel.config：今回実行した最小Linux 6.18.3設定。実機用設定とは別。

実SBI/SM/PMP/driver/SDK/Eyrie/sampleを実行し、モックは使用しない。
必要なkernel・driver・RISC-V実行ライブラリー・sampleを含むinitramfsを準備してから実行する。
[実行例、結果、検証範囲と全UART](../../../doc/jupiter2-utm-host-access-issue.md#6-実qemuでのsample回帰試験結果)を参照。
referenceケースのPASSは期待した旧版の失敗の再現成功であり、sample正常終了ではない。
