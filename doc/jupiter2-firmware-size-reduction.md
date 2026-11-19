# Jupiter2 OpenSBIとKeystone SMの容量削減調査

調査日：2026-11-20（JST）。ソース基準：`9889a16ab716a6549da45f2093b22160caa75a37`。
OpenSBI/SMソースと基準commitの差分なし。実験では別出力ディレクトリとcompiler wrapperを使い、
製品のビルド設定・リンカースクリプト・PMP保護を変更していない。

## 結論

**384 KiBのOpenSBI区画に収められる見込みは高い。同じ機能設定のままSMに`-O2`を指定すると、
今回の最終ITBは271,903 bytesとなり、393,216 bytesに対して121,313 bytesの余裕ができた。**

現在のSMビルドには最適化指定がなく、Clangの通常の既定値`-O0`でコンパイルされる。
OpenSBI本体は既に`-O2`である。まずSM側の最適化指定を正式なbuildオプションとして導入し、
コンテキスト切替・PMP・IPI・timer・MPRVの実ゲスト回帰を通すことを推奨する。
今回の実験はコンパイル・リンク・包装・容量確認までで、QEMU guestと実機の起動は未検証。

## 測定条件と結果

ユーザーの失敗ログではITBは533,191 bytes、超過139,975 bytesだった。
今回の基準buildはBIN 532,392 bytes、ITB 534,047 bytes。
ユーザーのELF・toolchain・FIT tool版は取得していないため、同一バイナリーの再現とは扱わない。
FITヘッダー・padding等の違いを含め、最終ITBの実サイズで比較する。

| SM compile条件 | .text | BIN | 最終ITB | 384 KiBに対する余裕 |
| --- | ---: | ---: | ---: | ---: |
| 現行相当（最適化指定なし） | 214,296 | 532,392 | 534,047 | −140,831 |
| `-O2` | 178,312 | 270,248 | 271,903 | 121,313 |
| `-Os` | 169,176 | 270,248 | 271,903 | 121,313 |
| `-Oz` | 168,472 | 270,248 | 271,903 | 121,313 |
| `-Os -ffunction-sections -fdata-sections` | 163,296 | 270,248 | 271,903 | 121,313 |

単位はすべてbytes。.textはSMとOpenSBIを最終リンクした全体の値。
[測定値とSHA-256のCSV](jupiter2-firmware-size-measurements.csv)に各候補を記録した。

共通条件：

- Clang/LLD/LLVM 19.1.7（Debian `19.1.7-22+b1`）、mkimage/dumpimage 2023.01。
- `k3_keystone_audit_defconfig`、SMのISA/ABIは既存のrv64imafdc_zicsr_zifencei／lp64。
- SM trace無効、`K3_PMP_BOOT_TRACE=1`、crypto provider unavailable、RNG auto。
- multimem有効、verification用FID無効。MPXY/OPTEED/RPMI/HSM等のconfigは削除していない。
- 各SM候補30/30 translation unitsのcompile成功、OpenSBIリンク成功。
- 既存ITSをそのまま使用。load/entry `0x100000000`、compression none。

## なぜ約256 KiB小さくなるか

[現行SM compiler](../keystone/sm/tools/k3_rv64_compile_audit.py)の`flags`には
`-O`指定がなく、関数・データ単位sectionも指定されていない。一方、
[OpenSBI Makefile](../opensbi/Makefile)は通常buildで`-O2`、section分割とGCを使う。
SMは別工程でコンパイルしたrelocatable objectなので、OpenSBI側の`-O2`はSMへ適用されない。

さらに[fw_base.ldS](../opensbi/firmware/fw_base.ldS)には、PMPのRX/RW分離に合わせて、
text/rodata/dynsym/rela.dynのサイズから書込み可能領域を2の冪境界へ配置する処理がある。
単純に機械語が36 KiBほど減るだけでなく、この境界が下がることが大きく効く。

| 項目 | 現行相当 | SM `-O2` |
| --- | ---: | ---: |
| `.text` | 214,296 | 178,312 |
| `.rodata` | 47,384 | 47,424 |
| `.rela.dyn` | 12,216 | 12,168 |
| `.data`開始アドレス（link上のoffset） | 524,288（512 KiB） | 262,144（256 KiB） |
| `.got`末尾から`.data`直前までの空白 | 244,512 | 19,296 |
| `.data`サイズ | 8,088 | 8,088 |

BINは途中のアドレス間隔を保持するため、大きな空白もファイル容量になる。
`-O2`ではこの空白が約220 KiB減り、最終BINは正確に262,144 bytes小さくなった。
`-Os`や`-Oz`でtextがさらに減っても、同じ256 KiB境界と同じdata末尾を使うため、
今回のBIN/ITBの長さは同じになる。内容やSHA-256が同じという意味ではない。

`.bss`は今回33,424 bytesだがNOBITSであり、raw BINをそのまま33 KiB増やすものではない。
ELFのdebug情報もraw BINの容量要因ではない。実際に基準ELFをstrip-debugしてから
BINへ変換し、元BINとバイト一致することを確認した。

## 削減候補の判断

| 候補 | 判断 |
| --- | --- |
| SMへ`-O2`を追加 | 最優先。今回これだけで収まる。OpenSBI側と同水準で、機能config変更を伴わない |
| SMへ`-Os`／`-Oz` | 代案。textの余裕は増えるが、今回の最終ファイル長はO2と同じ。性能とtimer応答を別途測る |
| 関数・データsection分割 | 二段階目。未参照部分のGCを可能にする。最終ITB長は今回さらに減らないので先行必須ではない |
| trace/loggingの削減 | 補助候補。今回SM trace off・PMP boot trace onのままで収まった。診断機能を先に消す必要はない |
| OPTEEDや未使用device driverを削る | 初手には不要。実機DT/RPMIとの依存、将来のOP-TEE同居要件を確認して別profile化する場合のみ |
| crypto実装を削る | 初手には不要。今回は既存provider-unavailableのまま保持。attestation/sealingの機能保証は追加されない |
| debug情報をstripする | raw BIN/ITBの削減には今回効果なし |
| linkerの2の冪alignmentを緩める | 採用しない。PMP領域分割・hash範囲・loader等との整合を変える。最適化だけで足りる |
| 圧縮、LTO、NOR区画拡張 | 今回の容量対策として不要。採用する場合はFSBL/再配置/asm/PMPへの影響を別に設計 |
| PMP/HSM/失敗時gateを無効化する | 採用しない。容量条件と隔離条件を混同しない |

`sm_init`、`pmp_set_global`、`k3_keystone_pmp_assert_active`、`k3_keystone_timer_enter`、
HSM start、Keystone SBI handler、domain context entryのsymbolがO2版にも残ることを確認した。
これは接続の静的確認であり、保護や機能が正常動作するという実行証拠ではない。
最適化により潜在的な未定義動作・inline asm制約の問題が表面化する可能性はあるため、
容量が収まるだけで実機向け成果物として採用しない。

## O2候補の再現手順

開発ホストのrepository rootで実行する。LLVM、Clang、LLD、FIT toolは
[導入手順](milkv-jupiter2-stack-install.md)の依存に加えて用意する。
既存buildディレクトリを使わず、未使用の作業先を指定する。
以下はcompiler wrapperで実験する手順であり、通常buildの既定値は変更しない。

```bash
set -euo pipefail
STUDY="$PWD/work/firmware-size-o2"
test ! -e "$STUDY"
mkdir -p "$STUDY/objects"
CLANG_REAL=$(command -v clang)
printf '#!/bin/sh\nexec "%s" "$@" -O2\n' "$CLANG_REAL" > "$STUDY/clang-o2"
chmod +x "$STUDY/clang-o2"
KEYSTONE_MULTIMEM=1 KEYSTONE_VERIFICATION=0 \
python3 keystone/sm/tools/k3_rv64_compile_audit.py \
    --opensbi "$PWD/opensbi" --output "$STUDY/objects" \
    --compiler "$STUDY/clang-o2" --rng auto --crypto unavailable
ld.lld -m elf64lriscv -r -o "$STUDY/sm-combined.o" "$STUDY/objects/"*.o
bash scripts/build_opensbi_link.sh "$PWD/opensbi" "$STUDY"
FW="$STUDY/build-opensbi-k3-keystone/platform/generic/firmware"
llvm-size -A "$FW/fw_dynamic.elf"
python3 scripts/build-jupiter2-install-image.py \
    --firmware-only --firmware-bin "$FW/fw_dynamic.bin" \
    --capacity-bytes 393216 --output "$STUDY/package"
python3 scripts/check-jupiter2-install-capacity.py \
    --capacity-bytes 393216 --image "$STUDY/package/bundle/firmware/fw_dynamic.itb"
```

baselineと同条件比較する場合は、未設定のKEYSTONE_SM_TRACE/crypto等を環境から引き継がないこと。
上記compile呼出しは`--trace`を付けず、crypto unavailableを明示している。

## 正式採用までの作業

1. SM buildへ最適化レベルを明示するオプションと成果物manifestを追加する。
   フラグ変更で古いSM objectを再利用しないことを確認する。
2. O2版を再リンクし、実際のtoolchain/ITSで最終ITBを再計測する。
   393,216 bytes以下と確認し、source/config/ELF/BIN/ITBのhashを保存する。
3. 対応QEMU guestで既存suite・robustness・Sstc on/off・2/16 hartの回帰を確認する。
   既知FAILと新たなFAILを分離し、compile/link成功をguest PASSとしない。
4. 実機入力DT、X100/A100のPMP、全hart IPI、M_TIMER、ロード範囲等の条件を確認する。
   容量に収まったことでこれらの未確認条件が解消したとは判断しない。
5. [実機導入・復旧手順](milkv-jupiter2-stack-install.md)に従い、復旧可能な順序で実機確認する。

今回、製品既定値の変更、実機書込み、QEMU guestの実行は行っていない。
新しい機能不具合の実証はなく、最適化未指定とlinker alignmentを容量上の要因として特定した。
