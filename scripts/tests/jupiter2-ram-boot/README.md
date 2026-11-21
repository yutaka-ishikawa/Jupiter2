# RAM起動用ホスト回帰試験

ここに置くのは開発PCで実行するテストスクリプト。実機へ送るコードではない。
それぞれの先頭コメントにも目的と検証範囲を記載している。

| スクリプト | 目的 | 実際に使うツール |
| --- | --- | --- |
| test_fit_packaging.py | FIT生成、ハッシュ、全ESOS loadables、LZO展開後の配置、不正入力の拒否 | dtc/mkimage/dumpimage/lzop |
| test_elf_rpmi_contract.py | ELF entryからDTへの反映、有効RPMIサーバーの選択とAP側DTの整合 | RISC-V対応clang/ld.lld、dtc |
| test_host_operations.py | 操作ツールのchecksum/dry-run、UART起動コマンドの生成・構文、同梱配置 | 実FITツール、bash -n、sha256sum |
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
