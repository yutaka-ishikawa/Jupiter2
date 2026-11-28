# Keystone関連不具合報告書・継続管理台帳

登録・更新日：2026-11-09（日本時間）  
初版対象：本リポジトリ `c6aa79100` までに確認・記録し、その後追記したSDK、Eyrie、SM、driverと移植接続部分。
過去の発見日を新しく推測せず、下記IDの登録日は本書の作成日とする。

## 取り扱いと状態

本書の「Keystone関連」は対象システムの分類であり、すべてを上流Keystoneの責任と
断定する意味ではない。元ソース、ビルド環境、K3/OpenSBI移植、周辺ツールを区別する。
上流最新版との照合がない項目を「上流で現在も再現する」と報告しない。
これはリポジトリ内の報告書であり、上流issue trackerへ提出済みではない。

- **修正済**：修正コードがこのリポジトリにある。全条件の実機検証完了とは限らない。
- **一部修正**：対象の一部で修正済みだが、旧経路等に残る。
- **未修正**：ソースで問題を確認したが、修正は未実装。
- **要確認**：契約・制約上の課題。単独で確定したバグとは扱わない。
- 確認方法は「実ゲスト観測」「生成機械語」「ソース確認」「ユーザー報告」を区別する。

ユーザーから既存verificationsの全PASS報告を受領済み。その全PASSは新実装前の報告であり、
新しい3002/3003の成功経路や異常系が試験済みという意味ではない。
新実装は通常profileで未対応、明示的qemu-dev profileで有効となる。PMP失敗注入、競合、実機の全条件も
全PASS報告から推定しない。過去のホスト模擬試験は削除済みで、現行試験の証拠には使わない。

## 一覧

| ID | 問題 | 主な対象・由来 | 状態 |
| --- | --- | --- | --- |
| KSB-001 | memset/strlenの自己再帰化 | SDK／ツールチェーン依存 | 修正済 |
| KSB-002 | 1352-byte reportを2048 bytesコピー、失敗時もコピー | Eyrie取込コード | 修正済 |
| KSB-003 | attestation入力の事前長検査・コピー結果検査不足 | Eyrie取込コード | 修正済 |
| KSB-004 | sealing出力サイズ・コピー結果の検査不足 | Eyrie取込コード | 修正済 |
| KSB-005 | sealing引数のSM検査・可変長作業領域 | SM取込コード | 一部修正 |
| KSB-006 | report検証前の入力長・data_len検査不足 | SDK verifier取込コード | 修正済 |
| KSB-007 | random statusを未検査、getrandom成功数・flags等 | Eyrie取込コード | 修正済 |
| KSB-008 | freestandingコードのstack protector依存 | build／移植環境依存 | 修正済 |
| KSB-009 | raw loaderのPIE/GOT・再配置依存 | loader／移植環境依存 | 修正済 |
| KSB-010 | Eyrie固定入口にbuild-id note | Eyrie／既知上流にも同じ前提 | 修正済 |
| KSB-011 | CMA開始PAの2 MiB整列を仮定 | Eyrie／配置制約 | 修正済 |
| KSB-012 | 明示DESTROY後の二重DESTROY | SDK取込コード | 修正済 |
| KSB-013 | MAX_PAGE_ORDERの最大値を除外 | driver／Linux版互換 | 修正済 |
| KSB-014 | 4 GiB超RAMに32 bit DMA制約 | driver／K3移植制約 | 修正済 |
| KSB-015 | FINALIZE前EID=-1のunsigned判定 | driver取込コード | 修正済 |
| KSB-016 | 64 bit EIDの切り詰め | SM取込・移植コード | 修正済 |
| KSB-017 | DESTROYの所有・PMP失敗時の解放 | SM取込・移植コード | 修正済 |
| KSB-018 | RUN/RESUMEでPMP失敗後も切替 | SM/OpenSBI移植 | 修正済 |
| KSB-019 | trap frame/status/PCの二重更新 | SM/OpenSBI移植 | 修正済 |
| KSB-020 | TOR PMPを読み戻し検査で拒否 | K3 PMP移植 | 修正済 |
| KSB-021 | HSM停止禁止とshutdownの不整合 | K3/OpenSBI統合 | 修正済 |
| KSB-022 | config変更でcarrayドライバ表が更新されない | OpenSBI build統合 | 修正済 |
| KSB-023 | report未使用data末尾の未初期化 | SM取込コード | 修正済 |
| KSB-024 | HKDF最大出力で8 bit loop counterがwrap | SM暗号ライブラリ | 修正済 |
| KSB-025 | hosted verifierをnative eappへリンクしてcanary参照が未解決 | 今回のverification統合 | 修正済 |
| KSB-026 | native入口でgp未初期化のまま緩和済み命令を実行 | SDK/native build統合 | 修正済 |
| KSB-027 | STOPの要求検査前の状態変更・未使用a1の不定値 | SM取込／OpenSBI移植契約 | 修正済 |
| KSB-028 | QEMUでM_TIMER方針のplatform hookが未適用 | OpenSBI移植 | 修正済 |
| KSB-029 | makeselfの短いpipe readでchecksum誤判定・展開切断 | 外部展開tool／試験経路 | 修正済 |
| KSB-030 | trap_vector_enclaveが4-byte未整列でmtvecへ設定されない | SM/OpenSBIリンク移植 | 修正済 |
| KSB-031 | 過去のSstc offでtimer取消し後の中断0 | 現行は再実行全PASS・過去原因未確定 | 要確認（履歴のみ） |
| KSB-032 | multimem有効化とエラー処理 | SM plugin／K3ビルド統合 | 修正済・実QEMU PASS |
| KSB-033 | FINALIZE失敗後のdriver IDR | 既存Linux driver | 修正済・実QEMU PASS |
| KSB-034 | 新規backingのhost復帰時PMP | 本作業の未公開草稿 | 修正済・実QEMU反復PASS |
| KSB-035 | SDKのhost資源の解放不足 | 既存SDK・ソース確認 | 未修正・4000のページ回収とは別 |
| KSB-036 | untrusted例のcount未初期化 | 上流サンプル取込ソース | samples側修正済・実QEMU PASS（元版保持） |
| KSB-037 | tests runnerが失敗でも0、retval探索先の不一致 | 上流examples/tests | samples側修正済・実QEMU PASS（元版保持） |
| KSB-038 | fib-benchのrdcycleがillegal instruction | hostのcounter許可に依存 | samplesをrdtimeへ適合・実QEMU PASS |
| KSB-039 | 新共通runnerがLinux syscall OCALLを配送しない | 本作業の草稿 | 修正済・実QEMU PASS |
| KSB-040 | attestor自身の2048-byte転送・status未検査 | 上流examples/attestation | samples側修正済・実QEMU PASS（元版保持） |
| KSB-042 | EXIT後のRESUMEが再進入を許す | EXITが再開可能なSTOPPEDへ遷移 | EXITEDを追加し、16 hart QEMUで再開拒否とDESTROYを確認 |
| KSB-043 | 並行PMP更新の一時競合でDESTROYが回収不能になる | K3移植のHSM/PMP admission | 実QEMUで再現・未修正 |
| KSB-044 | CREATE失敗時のPMP rollback結果を検査しない | SM CREATE cleanup・由来未確定 | ソース確認・障害注入による実証前 |
| KSB-045 | MPXY共有メモリーの丸め値がbytesではなくpage数になる | OpenSBI取込コード・上流修正照合済み | 修正済み（`d32afa86c`）・実ゲスト未検証 |
| KSB-046 | MPXY属性範囲のu32加算overflow | OpenSBI取込コード・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-047 | PMU counter indexの加算overflow | OpenSBI取込コード・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-048 | PMU event infoのサイズ乗算overflow | OpenSBI取込コード・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-049 | DBTR trigger範囲のoverflowとexact-end拒否 | OpenSBI取込コード・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-050 | RPMI共有queueの最小容量検査不足 | OpenSBI transport・上流修正照合済み | 未修正・DT依存、実ゲスト未検証 |
| KSB-051 | RPMI queue_id=countを受理 | OpenSBI transport・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-052 | SBI拡張名文字列の容量超過 | OpenSBI共通処理・上流修正照合済み | 未修正・拡張列/容量依存、実ゲスト未検証 |
| KSB-053 | HSM拒否前に対象hartの起動contextを更新 | OpenSBI共通処理とK3 admissionの統合 | 未修正・ソース確認、実ゲスト未検証 |
| KSB-054 | domain subset計算でXLEN幅shift | OpenSBI旧path・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-055 | RPMI CPPC要求のfield順序が上流修正前 | OpenSBI wire ABI／server互換性制約 | 修正候補・K3 server照合待ち |
| KSB-056 | PMU FW counter探索失敗時の配列index | OpenSBI取込コード・上流修正照合済み | 未修正・ソース確認、実ゲスト未検証 |
| KSB-057 | RAM FIT作成が共通ESOS構成・LZOを扱えない | 本リポジトリの実機導入ツール | 修正済・ホスト検査のみ |
| KSB-058 | Jupiter2 RPMI小領域と4 KiB PMP粒度の不一致で起動停止 | K3/OpenSBI domain登録とKeystone統合 | 粒度検査通過を実機確認・後続KSB-059で停止 |
| KSB-059 | 実機root PMP 14個＋Keystone最低3個で16個を超過 | K3実機と現行slot割当の制約 | X100のroot配置・SM初期化を実機確認、A100はKSB-071で停止 |
| KSB-060 | boot preflightが正規rootのロック付きRCPU保護も拒否 | K3 root PMPと後段admissionの契約 | X100で正規ロックの検証通過を実機確認、A100はKSB-071で停止 |
| KSB-061 | 共有bottom PMP slot解放時に他の利用者の予約も外れる | SMのPMP region allocator | 修正候補・SMコンパイル済・実機未検証 |
| KSB-062 | K3のOS/UTM共用slot切替で後段fallbackがOSメモリーを許可 | K3 PMP fallbackとEnclave切替 | 修正候補・SMコンパイル済・実機未検証 |
| KSB-063 | RAM起動後のUFS power mode／descriptor通信が失敗 | Jupiter2 RAM起動・U-Boot UFS | 参照構成とESOS整合修正後のUFS・Linux起動を実機確認 |
| KSB-064 | 参照ESOS結合スクリプトのdescription一致とconf_dualが不一致 | 第三者K3手順を今回の入力へ適用する場合 | 統合上の制約・明示構成による回避実装、ホスト検査済 |
| KSB-065 | 参照FSBLがESOS開始失敗を成功として扱いRAM追加FITも誤判定 | 参照U-Bootと販売元ESOSの統合 | core 1応答待ち失敗を実機観測・診断修正候補 |
| KSB-066 | 診断版のRCPU entryがSPLで0xxと表示される | 本リポジトリの診断パッチとtiny printf | 表示修正を実機確認 |
| KSB-067 | 参照SPL DTのcore 1起動先が販売元ESOS ELF entryと不一致 | 固定参照FSBLと今回の販売元ESOSの統合 | 修正後の両core応答を実機確認・後段KSB-068で停止 |
| KSB-068 | 両RCPU応答後、OpenSBI引渡し直前の表示を最後に無出力 | 参照RAM起動と販売元OpenSBI/DTの統合 | KSB-069修正後にU-Boot到達を実機確認 |
| KSB-069 | OpenSBI用DTのRPMI queueが同梱ESOSの有効サーバーと不一致 | 参照U-Boot DTと販売元ESOSの統合 | 整合修正後のU-Boot・UFS・Linux起動を実機確認 |
| KSB-070 | Linux用DTがSMのM-only mailboxページ内の直接controllerを有効化 | Bianbu Linux DTとK3 SMの所有契約 | 提供DTBで不整合確認・別名DTBで限定修正候補 |
| KSB-071 | X100/A100のPMP数混在を16個固定の移植処理が拒否 | K3 Keystone移植のroot配置・PMP証拠管理 | 混在対応候補・QEMU実Linuxで二種成功、実機helloはKSB-073で停止 |
| KSB-072 | QEMU回帰試験が実機の混在PMP・粒度・domain条件を含まない | Jupiter2部分モデルと試験範囲の制約 | 混在PMP/4 KiBオプション実装、実機相当domain等は未実装 |
| KSB-073 | 全16 CPU起動後、hello二種のhost runnerがload access faultで停止 | K3の独立UTM割当てとホストPMP復帰の不整合 | SM修正・実QEMUで旧版の障害再現、修正版hello二種8回PASS、実機再試験待ち |
| KSB-074 | OPTEEDの呼出元・メッセージ長・切替結果の検査不足 | OpenSBI取込コードとK3 Keystone切替ガードの接続 | 修正済み（`4b0f75220`）、実ゲストのMPXYは未検証 |
| KSB-075 | ドメイン切替でSstcタイマー期限を引き継ぐ | OpenSBIドメインコンテキストに `stimecmp` がない | 試験的な変更を取り消し、同居時の影響は未確認 |
| KSB-076 | OP-TEE先行起動でK3 Keystoneの初期PMP設定が停止 | K3移植のPMP検査と配置が起動時のLinux所属を前提とする | K3 QEMUでOP-TEEの16 hart初期化と主hartのLinux引き渡しを確認 |
| KSB-078 | OP-TEE先行起動後にLinuxが副hartを開始できない | 既存のドメイン終了が内部HSM停止を必要とし、K3は全停止を拒否 | 初回引き渡しの内部停止を実装し、K3 QEMUでLinuxの16 CPU起動を確認 |
| KSB-079 | OP-TEEとのPMP更新競合でKeystoneのDESTROYを再試行できなくなる | 排他の試作と既存のDESTROYING隔離処理の組合せ | K3 QEMUで `-EAGAIN`、明示再試行とclose後の破棄、TA応答を確認 |
| KSB-080 | OP-TEEの16 CPU並行TA試験がPMP詳細ログでタイムアウト | OpenSBIの実行時切替で毎回PMP配置の全領域をUARTへ出力 | 実行時の詳細出力を抑制し、K3 QEMUで並行TA応答を確認 |
| KSB-081 | Keystoneの遅延DESTROY中にOP-TEEのRPC復帰が失敗する | MPXY経路がPMP予約競合を再試行せず、Linux側が応答を引き続き処理する | LinuxでMPXY要求を再試行し、K3 QEMUのclose競合でTA応答を確認 |
| KSB-082 | 同居ゲストのEnclave実行中に外部割り込みで停止 | IMSIC経由のM-mode IPIをEnclave用トラップが処理しない | K3 QEMUでLinuxのRFENCEを処理し、TAとEnclaveの完了を確認 |
| KSB-083 | 同居ゲストがOP-TEEの副hart初期化で停止 | HSM起動完了時の一時的なゲート競合で副hartを停止 | 取得を再試行するよう修正し、K3 QEMUで強制競合と反復起動を確認 |
| KSB-084 | QEMUのfTPMモジュール登録中に間欠的にタイムアウト | OP-TEE実行中のhartがLinux向けSBIソフトウェアIPIの宛先から外れる | Linux宛てIPIを保持するよう修正。16 hart QEMUでfTPMと同居試験が成功 |
| KSB-085 | 並行CREATE／DESTROY時に全hart PMP更新が失敗する | ローカル切替のゲート競合でhartが停止。固定回数のACKポーリングでも早期打ち切り | PMP状態の確認とACK待ちを修正 |
| KSB-086 | fTPM同居QEMUでEnclaveのCREATEが間欠的に失敗する | PMP ACK待ちとRFENCE待ちが競合 | ACK待ちでローカルのRFENCEを処理。修正後の16 hart同時実行試験は5回合格 |
| KSB-087 | fTPMの永続化失敗時にNV_Writeが成功を返す | 採用したfTPM TAの既存実装でNV書き戻し失敗がTPM結果に伝わらない | 16 hart QEMUで確認。未修正 |
| KSB-088 | OP-TEE同居試験が入力DTB不足で起動できない | 同居用DTBとinitramfsの生成経路が未登録 | 生成スクリプトと入力DTSを追加 |
| KSB-089 | OP-TEE同居ゲストの `/init` が命令アクセスフォルトで停止 | 起動DTB用PMP領域のLinux予約漏れを確認。報告時のフォルト物理アドレスは未確認 | 予約を追加し、既存の同居試験で回帰確認 |
| KSB-090 | 既定の同居DTBでfTPMデバイスが作られない | `microsoft,ftpm` のノードが未定義 | 同居用DTSにfTPMノードを追加 |
| KSB-091 | fTPM・IMAゲストの初期化がタイムアウトする | 固定DTSで起動時の乱数シード欠落を確認。タイムアウトとの因果は未確定 | 試験ごとに新しいシードを供給 |
| KSB-092 | 実機の同居RAM起動がOpenSBIのPMP初期化で停止 | 同梱FITとUARTから現行規則で21枠相当を確認 | Pico-ITXの固定配置を実装。実機でOpenSBIのPMP初期化を通過しCore起動へ到達 |
| KSB-093 | 実機同居用のOP-TEE起動DTBが読み取り専用 | OP-TEEの外部DTB初期化と領域のR権限が不整合 | 実機UARTでCore内への複製とCore起動を確認 |
| KSB-094 | 対応するMPXY初期化が失敗しても起動を継続 | FDTドライバーの失敗がgenericプラットフォームへ返らない | K3 Keystone構成で失敗を返し、QEMUでS-modeへの引き渡し前に停止を確認 |
| KSB-095 | OP-TEE単独の並行TA試験で停滞 | 16 hartのK3 QEMUでタイマー割り込みによるOP-TEEからの復帰と再試行が続く | OpenSBIが切り替え前の競合を返すよう修正。QEMU単独試験10回合格 |
| KSB-096 | fTPM・IMA試験のゲストがLinux起動前に停止 | PMP読み戻し後の起動台帳更新が一時的なロック競合で失敗し、副hartが停止 | 台帳を取得順に更新。KSB-097との修正版でQEMU起動40回合格 |
| KSB-097 | OP-TEEからの副hart起動要求が間欠的に失敗 | 別のhartのHSM起動処理が共有ゲートを使用中だと、起動要求の発行側が即時に失敗 | 初回起動とLinuxへの引き渡しで取得を再試行。KSB-096との修正版でfTPM・IMA合格 |
| KSB-098 | 実機USB RAM起動でOP-TEE登録後にU-Bootへ進まない | OpenSBIのドメインコンテキスト確保が `SBI_ENOMEM (-1004)`。QEMUの106 KiB構成で割り当て管理枠の枯渇を確認 | 同梱FITを192 KiBに修正。QEMU同居に合格し、実機USB RAM起動でU-Boot本体のプロンプトまで確認 |
| KSB-099 | Pico-ITX同梱FITでLinuxの副hart 1〜15が起動しない | OP-TEE終了後にハードウェアHSMで再開。OpenSBIがPMP設定を省略し、枠0の読み戻しに失敗 | `223c5f2` でPMP再設定を実装。QEMUで保持時と消失時を確認。実機再試験待ち |
| KSB-100 | Pico-ITX同梱FITで組み込みwatchdog初期化がpanic | `spa_wdt_probe()` が保護中のMPMU ARSRを読み出す。現行のMMIO仲介に該当レジスタがない | `223c5f2` でMMIO仲介を追加。ELFと実機用FITを照合。watchdog実機試験待ち |
| KSB-077 | KeystoneのPMP初期化で設定ビットが別の枠に残る | `pmp_init()` が `PMP_SET` の更新値をループ間で再利用 | K3で枠ごとの消去に修正、QEMUで枠13の拒否が解消 |
| KSB-041 | attestor統合時に負荷・2 OCALLのループを削除 | samples統合の変更 | 復元済・Sstc on/off実QEMU PASS |

「取込コード」は本リポジトリで修正前のコードを確認できるという意味。
KSB-010およびKSB-045〜056以外の上流所在・上流最新の修正状態は、この台帳で新たに照合したものではない。

## KSB-001: SDK memset/strlenが自身を呼ぶ機械語になる

- **対象**：[SDK app CMake](../keystone/sdk/src/app/CMakeLists.txt)、[string.c](../keystone/sdk/src/app/string.c)。
- **症状・条件**：最適化buildの乱数eappがOCALL前に終了。store page faultの
  障害VAは `0x3ffdfff0`、128 KiBユーザースタックの下端 `0x3ffe0000` より16 bytes低い。
- **原因・影響**：自前のbyte loopをGCCがmemset/strlen呼び出しへ変換。
  特に4098 bytesのstorage初期化はmemsetのbyte loop側へ入り、同じ引数の再帰でスタックを消費する。
- **根拠**：実SDKの修正前string.c.oとリンク済みeappに自己呼び出しを確認。
  ユーザーの厳密なPC→命令対応にはそのELFが必要だが、ログのスタック下端超過と整合する。
- **修正**：`2c99fb066`。eapp archiveにfreestanding/no-builtin、GCCのstring.cへ
  loop pattern変換禁止を設定。[機械語チェック](../scripts/check-keystone-eapp-string.py) をbuild時に追加。
- **検証**：修正前objectはチェック失敗、修正後は成功。SDKとverification再build成功。
  その後ユーザーから全verification PASS報告あり。標準的な全GCC/Clang版を網羅した結果ではない。
- **詳細**：[停止原因と再試験](keystone-sdk-string-recursion.md)。

## KSB-002: report出力の固定2048-byteコピー

- **対象**：[Eyrie syscall](../keystone/runtime/call/syscall.c) のATTEST_ENCLAVE。
- **確認**：SM/SDK reportは1352 bytesだが、`copy_to_user(..., 2048)` を固定実行している。
  このコピーはSBIの成否にも依存しない。ソース確認、異常ケースのゲスト再現は未実施。
- **影響**：仕様どおり1352 bytesを用意したアプリでは後続696 bytesへの書き込みになる。
  作業バッファのreport外や以前の内容まで返す可能性がある。
- **発見時の状態**：未修正。K3側で3002は無効だが、Eyrie側のコピー処理は別に存在する。
  SMが未対応を返すことだけで、このコピーが実行されないとは扱わない。
- **当初の修正計画**：成功時だけ共通型の正確なsizeofをコピー。戻り値確認、buffer初期化・消去。
- **受入試験**：1352 bytes前後のcanary、失敗status時の出力不変更、コピーfaultのerror伝播。
  [同時実装計画C4](keystone-sbi-3002-3003-joint-plan.md) で対応する。

更新（3002/3003共通実装）：成功時のみ共通reportサイズ1352 bytesをコピーし、copy結果も確認。
実装箇所とbuild結果は [実装記録](keystone-sbi-3002-3003-implementation.md) を参照。
新しいゲスト正常・異常系はコード作成済みだが、統合実行は未確認。修正commitは本更新の履歴を参照。

samples統合時の追記：元attestor自身にも2048-byte OCALL転送が残る点をKSB-040として
別登録した。統合コピーでは正規型と成功検査へ適合したが、元examplesを変更したとはしない。

## KSB-003: attestation入力コピー前の検査不足

- **対象**：同じEyrieの3002経路。
- **確認・影響**：arg2の1024上限等を検査する前にcopy_from_userを呼び、その結果も確認しない。
  runtimeの作業bufferに対する過大入力、部分コピーや不正VAを正常な入力として処理し得る。
  SM側の後段の長さ検査では、既に行ったEyrieのコピーを保護できない。
- **発見時の状態**：未修正、ソース確認。SMで3002が無効でも前処理は別途修正が必要。
- **対応・試験**：長さ・overflow・全VA範囲を先に検査し、copy結果を確認。
  0/1024/1025、NULL、不正VA、境界跨ぎと後続正常要求の復帰を実QEMUで確認する。

更新（3002/3003共通実装）：runtime共通入口で長さ・VAを先に検査し、copy errorを伝播。
実装箇所とbuild結果は [実装記録](keystone-sbi-3002-3003-implementation.md) を参照。
新しいゲスト正常・異常系はコード作成済みだが、統合実行は未確認。修正commitは本更新の履歴を参照。

## KSB-004: sealing出力capacityとコピー結果の検査不足

- **対象**：EyrieのGET_SEALING_KEY、[SDK型](../keystone/sdk/include/app/sealing.h)。
- **確認**：必要出力は192 bytes。現行runtimeはcapacityの上限しか確認せず、小さい値も受け付け、
  成功後に渡されたcapacityだけコピーする。入力・出力copyの戻り値も未確認。
- **影響**：不完全なkey structを成功として返す、大きいcapacityでstruct外までコピーする、
  copy失敗を呼び出し側へ伝えない。実際の残留内容・異常実行は未検証。
- **発見時の状態**：未修正。現K3 SMでは3003が無効。
- **対応・試験**：最低192のcapacity検査、成功時192だけコピー、copy error伝播と作業buffer消去。
  capacity 0/191/192/193、末尾canary、不正VAを確認する。

更新（3002/3003共通実装）：capacity>=192を検査し、成功時192 bytesだけ返却。両作業bufferを消去。
実装箇所とbuild結果は [実装記録](keystone-sbi-3002-3003-implementation.md) を参照。
新しいゲスト正常・異常系はコード作成済みだが、統合実行は未確認。修正commitは本更新の履歴を参照。

## KSB-005: SM sealingの引数検査とVLA

- **対象**：[get_sealing_key](../keystone/sm/src/enclave.c)、[sm_derive_sealing_key](../keystone/sm/src/sm.c)。
- **確認**：入力identifier長に応じて `info[MDSIZE + key_ident_size]` をSMスタックへ確保する。
  helper内部には長さ・加算overflow・当該EPMの範囲を十分に検査する契約がない。
  sealing経路は渡されたポインタを直接使って導出・出力する。
- **影響**：無検査で有効化すると、過大な作業領域や契約外アドレスを処理する可能性。
  3003有効版での異常入力実行は未実施。現行K3では手前で拒否される。
- **発見時の状態**：未修正。Eyrieの制限だけをSM自体の引数保証とはしない。
- **対応・試験**：4096-byte上限、EPM所有権、PA契約、overflow、固定上限workspaceを共通実装。
  最大長・超過・UTM・他EPM・SM領域と後続要求の復帰を検証する。

更新（3002/3003共通実装）：K3の3003は新共通サービスへdispatchし、上限・所有権・固定workspaceを実装。汎用platform向けの旧helper/VLAは残るため一部修正。
実装箇所とbuild結果は [実装記録](keystone-sbi-3002-3003-implementation.md) を参照。
新しいゲスト正常・異常系はコード作成済みだが、統合実行は未確認。修正commitは本更新の履歴を参照。

## KSB-006: report verifierの入力境界検査

- **対象**：[Report.cpp](../keystone/sdk/src/verifier/Report.cpp) のfromBytes/checkSignaturesOnly等。
- **確認**：fromBytesには入力byte数がなく固定sizeofを読む。署名検証でreportのdata_lenを
  使う前に1024上限を確認する処理もない。stringfy側の検査は署名検証入口の検査とは異なる。
- **影響**：不正な生reportやdata_lenを渡した場合の範囲外読み取りが懸念される。
  fromBytesだけなら呼び出し元のcapacity契約も関係するため、APIの契約と検査の両方を整備する。
- **発見時の状態**：未修正、ソース確認。クラッシュ等の実行再現は未実施。
- **対応・試験**：長さ付きchecked入口、data_len上限、JSONの負数/過大値の検査。
  短い入力・不正長は署名処理や表示前に拒否する。

更新（3002/3003共通実装）：長さ付きfromBytesChecked/fromJsonCheckedとdata_len上限、hex形式、外部pin検査を追加。旧fromBytesの呼び出し元には従来のcapacity契約が残る。
実装箇所とbuild結果は [実装記録](keystone-sbi-3002-3003-implementation.md) を参照。
新しいゲスト正常・異常系はコード作成済みだが、統合実行は未確認。修正commitは本更新の履歴を参照。

## KSB-007: random/getrandomの戻り値・引数処理

- **対象**：Eyrieのcall/sbi.c、util/rt_util.c、call/linux_wrap.cとpage_swap利用箇所。
- **修正前**：a0 statusを確認せずa1を乱数として取得し、asmのa1出力指定も不十分。
  rt_util_getrandomはコピーやSMの成否を要求byte数へ反映しない。直接uintptr_t書き込みに
  非整列への依存があり、linux_getrandomはflagsを無視していた。
- **影響**：RNG失敗を成功値として扱う、書き込み失敗を成功扱いする等。
  非整列が必ず全CPUでtrapになるという意味ではない。
- **修正済**：`867a23e57`。checked a0/a1 API、端数コピー、status/errno伝播、flagsとVA検査。
  AT_RANDOMとswap鍵取得も失敗を無視しない。
- **検証**：実ゲストmatrixを含む全verification PASSのユーザー報告あり。
  ソース未提供の全hardware RNGエラー・全partial-copy経路まで網羅したとはしない。
  [3001実装記録](keystone-sbi-3001-implementation.md) を参照。

## KSB-008: freestandingコードとstack protector

- **由来**：通常Linuxコンパイラの既定設定への依存。すべての上流buildで発生するとは限らない。
- **影響**：Eyrie/native app等が提供しないstack-canary/libc支援を要求してbuild/linkに失敗。
- **修正済**：`fc7fe2044`。該当freestanding targetだけに-fno-stack-protectorを指定。
- **根拠・確認**：[累積記録第1節](keystone-cumulative-changes.md)。後続のクロスbuild成功。
  ホストrunner全体の保護を無効にする対応ではない。

## KSB-009: raw loaderのPIE/GOT依存

- **条件・影響**：raw imageはELF再配置を受けず任意EPMへコピーされるが、GOT経由の
  stack取得や絶対アドレス依存が残り、正しいstackを設定できない。
- **由来**：loaderと移植ツールチェーンの組み合わせ。上流最新版との再照合なし。
- **修正済**：`f1c0678e5`。PC相対lla、PIE/PIC/GP relaxation依存の除去、no-relax/GOT ASSERT。
- **確認**：入口配置チェックと後続build。詳細は[累積記録第2節](keystone-cumulative-changes.md)。

## KSB-010: 固定入口でbuild-idを実行

- **観測**：GDBでmepc=0xffffffffc0000000、mcause=2、mtval=4。
  入口にはGNU build-id noteのヘッダーが置かれていた。
- **原因**：固定入口へ飛ぶloaderと、開始コードを先頭へ保証しないlink配置の組み合わせ。
  上流 `b8c2385355b2afb5b94a4e5dc503936f1502b972` にも同じ前提があったことは過去に確認済み。
  build-id生成条件によるため、上流の全環境で常時発生するとはしない。
- **修正済**：`345f9d2bd`。専用entry section、先頭配置・ENTRY・ASSERT、note除去。
- **確認**：実ゲストhello成功報告、リンク検査。[詳細とGDB証拠](keystone-eyrie-entry-build-id.md)。

## KSB-011: CMA開始位置と2 MiB leafの整列制約

- **観測**：256 MiB級EPMのPA=0x104f00000でmm.cの整列assert、OCALL前に終了。
- **原因**：大きいEPMで2 MiB leafを選ぶが、CMAはその開始整列を保証しない。
- **由来**：Eyrieの既存配置制約が新しいCMA確保方法で表面化した互換性問題。
- **修正済**：`87efe630c`。非整列部は4 KiB leaf、必要なpage tableの確保とfree_base更新。
- **確認**：build/入口検査。後の全verification PASS報告には256 MiB正常系を含むが、
  すべてのPA配置・大きさを検証した意味ではない。[累積記録第9節](keystone-cumulative-changes.md)。

## KSB-012: SDK DESTROY後のEID残存

- **対象**：[KeystoneDevice.cpp](../keystone/sdk/src/host/KeystoneDevice.cpp)。
- **原因・影響**：明示destroy成功後もeidが有効なままで、destructor等が同じDESTROY ioctlを再発行する。
- **修正済**：`0977df6be`。成功後だけeid=-1にし、失敗時はIDを保持する。
- **確認**：実guestの明示DESTROYを使う正常系。詳細は累積記録第7節。

## KSB-013: 最大buddy orderの境界判定

- **対象**：[keystone-page.c](../keystone/linux-keystone-driver/keystone-page.c)。
- **原因**：Linux 6.8以降のMAX_PAGE_ORDERはinclusiveだが、旧MAX_ORDER同様に `<` で判定していた。
- **影響**：確保可能な最大orderを試さず、4 MiB級EPMの確保に失敗し得る。
- **修正済**：`6c32be5b3`。版ごとにinclusive/exclusiveを区別する。
- **確認**：4 MiB buddy確保の実ログと後続試験。[大容量EPM](keystone-large-epm.md)。

## KSB-014: K3高位RAMとDMA制約

- **原因・影響**：K3 RAMは4 GiB以上だが、32 bit DMA mask/DMA32前提の領域確保では
  CMA予約があっても使用できない。CPU PAとDMA handleも別の概念として扱う必要がある。
- **由来**：既存driverのplatform制約で、全platformでの上流不具合とはしない。
- **修正済**：`6c32be5b3`。64 bit DMA、dma_alloc_pages、CPU PA/解放handleの分離。
  確保・解放の状態初期化も同時整備。CMAの明示予約は起動側の設定要件。
- **確認**：256 MiB級CMA確保の実ログ。[大容量EPM](keystone-large-epm.md)。

## KSB-015: FINALIZE前のunsigned EID sentinel

- **対象**：[keystone-ioctl.c](../keystone/linux-keystone-driver/keystone-ioctl.c)。
- **原因**：未作成のeid=-1をunsignedへ格納しているのに、`eid >= 0` でSM DESTROYの要否を判定。
- **影響**：FINALIZE前のcleanupでもSMへ不正EIDを渡し、driver資源解放を妨げ得る。
- **修正済**：`6c32be5b3`。unsigned -1との明示比較。
- **検証範囲**：ソースと修正差分で確認。全初期化失敗位置の実guest網羅は未確認。

## KSB-016: EID全幅検査前の32 bit切り詰め

- **対象**：SM DESTROY/RUN/RESUME helper。
- **影響**：64 bit SBI引数を狭いenclave_idへ変換すると、範囲外の値が別の有効IDになり得る。
- **修正済**：`cc885e6ad`。型変換前に元の値全体で検査しINVALID_IDを返す。
- **確認**：ソース・修正差分、現行実ecallの無効ID試験。
  高位bitを変えた全値が現行guest試験に含まれるとはしない。

## KSB-017: DESTROYの所有権とPMP解除失敗

- **原因**：ALLOCATED/DESTROYINGも破棄対象に含め、global PMP解除失敗後でも資源解放・成功復帰し得た。
- **影響**：破棄処理の重複と、不明な保護状態の物理ページ再利用。
- **修正済**：`cc885e6ad`。許可状態とDESTROYINGへの移行を同じlockで管理し、
  PMP解除失敗時は未解放資源を保持してerrorを返す。
- **確認**：現行guestでは正常CREATE/DESTROYと再作成を実行。失敗注入・競合の網羅は未確認。
  [2002/2003修正報告](keystone-sbi-2002-2003-fixes.md)。

## KSB-018: PMP失敗を無視したcontext切替

- **原因・影響**：host context等を交換した後にPMP設定し、失敗でも切替を完了し得る。
- **由来**：SMとOpenSBI接続・PMP APIの失敗契約を含むため、上流への一括帰属はしない。
- **修正済**：`cc885e6ad`。設定成功後だけcontextを交換し、失敗時はstate/thread予約を復旧。
  権限復旧不能なら不明な状態でhostへ戻らず停止する。
- **確認**：正常RUN/STOP/RESUME/EXITは現行guest試験。PMP失敗・復旧失敗の全注入は未確認。

## KSB-019: OpenSBIの復帰フレームとKeystone ABI

- **条件・影響**：RUN/STOP/RESUME/EXITで交換したフレームを共通dispatcherが再更新すると、
  PC二重加算やa0/a1破壊になる。正のKeystone statusも標準SBI error処理へそのまま渡せない。
- **由来**：今回のOpenSBI移植接続部分。
- **修正済**：`75f5c0377`。skip_regs_update等で復帰処理を一元化しstatus ABIを保持。
  同時のK3タイマーポリシー調整は全実タイマーケースの証明ではない。
- **確認**：後続正常lifecycle/OCALL試験。詳細は累積記録第4節。

## KSB-020: K3のTOR読み戻し検証が無条件拒否

- **観測**：CMA確保成功後、CREATEが100003(PMP_FAILURE)で失敗。
- **原因**：K3移植のverified PMP設定がTORを明示拒否。OpenSBI pmp_getのNAPOT向け
  比較をTOR区間の検証へそのまま使えなかった。
- **修正済**：`59a848b72`。実CSRの上下境界・mode/権限・UNSET状態を検証する。
- **確認**：後続CREATE到達と全verification PASS報告。全hartの全CSR異常注入は未確認。
  [TOR原因と修正](keystone-tor-pmp.md)。

## KSB-021: HSM停止禁止とsystem resetの衝突

- **観測**：Keystoneを実行していなくてもshutdownでhart invalid stateとFailed stop hart。
- **原因**：全hart維持のK3ポリシーとOpenSBI終了順序が不整合。QEMU syscon reset driverも未設定。
- **修正済**：`4011d1c9d`。reset許可判定後platform resetへ直接委譲し、sysconを有効化。
- **確認**：buildとdriver収録を確認。現行run-allはshutdown/rebootの成功を検査するsuiteではない。
  実際の電源断・再起動は別に確認する。[reset報告](keystone-system-reset.md)。

## KSB-022: carray生成とconfig依存関係

- **観測**：defconfigを更新しても既存buildのdriver一覧が更新されずsysconが登録されなかった。
- **対象・由来**：OpenSBIのcarray生成規則。Keystone SM自体の不具合とは分類しない。
- **修正済**：`4011d1c9d`。生成規則にKCONFIG_AUTOHEADER依存を追加。
- **確認**：過去のbuild調査と修正差分。[reset報告](keystone-system-reset.md) に詳細。

## KSB-023: SM reportの未使用data末尾が未初期化

- **対象**：[attest_enclave](../keystone/sm/src/enclave.c)。
- **確認**：ローカルstruct reportを初期化せず、入力size bytesだけdataへコピーしている。
  出力はstruct全体なので、size<1024では未使用data末尾の内容も渡される。
- **影響**：SMスタックの残留内容をreportへ含める可能性。未使用末尾は署名対象でもない。
  Eyrie側の2048-byteコピーKSB-002とは別で、SM内で1352-byte reportを完成させる段階の問題。
- **発見時の状態**：未修正、ソース確認。現行K3では3002が無効のため実際の漏出内容は未観測。
- **対応・試験**：reportを全体ゼロ初期化し、入力sizeだけを署名する既存形式を維持。
  0/短いdata/1024の取得、連続要求での未使用末尾0を実QEMUで確認する。

更新：旧attest_enclaveのstruct初期化と新K3共通workspaceの全体初期化を実装。
build確認済み、report末尾0の実guest試験は作成済み・実行未確認。

## KSB-024: HKDF最大出力でloop counterがwrapする

- 登録日：2026-11-09。状態：修正済（本共通実装の変更）。
- 対象：hkdf_sha3_512.cのhkdf_expand。
- 原因：最大出力255 blocksを許可する一方、loop変数もunsigned charだったため、
  i=255の後に0へwrapし、loopを終えられない。i-1を使うコピー位置も範囲外になり得る。
- 根拠：最大長検査、div_ceil、loop変数とコピー式のソース確認。今回の3003出力128 bytesは2 blocksで、
  この最大長ケースには該当しない。上流最新版との比較は未実施。
- 修正：loop変数をintとし、HMACへ渡す1 byte counterを別にした。
- 検証：全SMのcompile/link、通常の32/128-byte KDFを使う実QEMU初期化を確認。
  最大16320-byte KDFの実行試験は未実施。3003のAPIは任意のKDF出力長を公開しない。

## KSB-025: hosted verifier archiveのnative eappへの流用

- 登録日：2026-11-09。状態：修正済（本更新）。
- 対象：SDK verifier CMakeとverifications/crypto/Makefile。今回の3002/3003統合で導入。
- 症状：ユーザー環境のGCC 13でcrypto eappのlink時に__stack_chk_guard/__stack_chk_failが未解決。
- 原因：通常Linux用libkeystone-verifier.aをnostdlib eappへリンクした。
  archive内のverify/sha3/ge/fe等にはstack protector参照があり、最終linkの
  -fno-stack-protectorではコンパイル済みobjectの参照を除去できない。
- 根拠：ユーザー添付linkログ。上流Keystoneの不具合とは帰属しない。
- 対応：hosted verifierは維持し、C暗号primitiveだけをnative設定で別archiveへbuildする。
  強制stack-protector設定で再buildし、archiveの参照と最終nostdlib linkを検査する。
- 修正：libkeystone-verifier-eapp.aを新設し、C暗号primitiveを
  -ffreestanding/-fno-builtin/-fno-stack-protectorでコンパイル。
  crypto eappだけが新archiveを使い、Linux runnerは従来archiveを使う。
  SDK build時に新archiveのcanary/C++ runtime依存を検査する。
- 検証：強制-fstack-protector-strong設定でもSDKとcryptoパッケージをbuildできた。
  hosted archiveにcanary参照が残ること、新archiveと最終eappには残らないことを確認。
  同じeappを旧archiveへlinkすると未解決が再現し、新archiveへ差し替えると成功する対照確認も実施。
  QEMU試験より前のbuild問題であり、実行時PASSとは別に扱う。
- 再実行：make cryptoでSDK・eapp・既知値を更新し、install-crypto/install-eyrie後にQEMU試験。
  本件の修正commitはこの報告項目とbuild設定の変更履歴を参照。

## KSB-026: native main直入とglobal pointer未初期化

- 登録日：2026-11-09。状態：修正済（本更新）。
- 対象：native eappの入口、SDK起動コード、verificationのlink設定。
- 症状：cryptoの両qemu-dev bootでload page fault、障害VA=0xfffffffffffffe28、
  unavailableでstore page fault、障害VA=0xfffffffffffff808。report返却は0件。
  同じログで3001の7ケースとhost側の3002/3003権限検査はPASS。
- 原因：nostdlibでmainを入口にし、CRTによるgp初期化を行わない一方、
  linker relaxationはgp相対アクセスを生成していた。
- 根拠：実際のcrypto ELFにlw variant,-472(gp)、addi output,gp,-2040等を確認。
  gp=0なら-472は報告のfe28と一致し、unavailableで出力VAが負になる症状にも一致する。
- 対応：SDKに専用native startを追加し、norelaxのPC相対命令でgpを初期化してからmainへcallする。
  検証用native eappの入口を変更し、ELF入口と実命令をbuild時に検査する。
- 修正：SDKのcrt.Sにkeystone_eapp_startを追加。norelax/norvcのllaでgpを初期化する。
  root build対象のhello-nativeと全native verificationのentryとarchive強制取り込みを指定。
  libc付きeappは既存CRTのまま。旧nativeサンプルで独自linker scriptを使うものは未変更。
- 検証：実ELF入口とAUIPC/ADDIの計算値が__global_pointer$に一致することをbuild時に検査。
  QEMU user-modeのSDK起動probeでmain直入はgp不一致(41)、新入口は正常終了(0)を確認。
  このprobeはLinux exitを使う独立CPUテストで、OpenSBI/SMの模擬試験や統合PASSではない。
  SDK、hello-native、全guestパッケージと既知値の再生成は成功。ゲストsuite再実行は未確認。
  ユーザー環境のELFの正確なPC対応はそのELFで再確認が必要。
  上流最新版の発生状況は未照合で、今回のnative build統合問題として管理する。

- 追加のユーザー実行結果：添付log.txt（今回受領）では修正後の
  `run-qemu.py --all` がqemu-dev 2 boot、unavailable 1 boot、乱数7ケースすべてPASS。
  この報告範囲でシステムゲスト統合の成功を確認。実機の検証結果ではない。

## 要確認事項・対象外との境界

- **PA/VA契約**：3002の既存copyはMPRVでVAを扱える場合があるため、
  「PAへ変換していない」という事実だけでは単独の確定バグとしない。
  3002/3003をEPM内PAへ統一する移植計画に対する適合性課題として管理する。
  satp/MPRV/PMPの意味と復帰を実QEMUで確認してから共通化する。
- 3002/3003の未実装provider、実機endorsement、paging追加機能、CMA容量不足、
  未マウント/procや古いdriverのロードは、それだけでKeystoneコードのバグとはしない。
- matrixがFAILの理由を表示しなかった点は試験ツールの診断不足で、`e1cbdabca`で改善済み。
  乱数eapp本体の停止原因KSB-001とは区別する。
- 本書は既知の発見と修正記録の整理。新たな網羅的な不具合調査を完了したものではない。

2026-11-09追記：samples統合でattestorと旧testsのコピーも専用CRTへ適合した。
元のkeystone/examplesは保持し、そちらのlink設定を変更したとはしない。

## KSB-027: STOP要求の事前検査と戻り値の明確化

- 状態：修正済（SBI 3004実装完了作業で登録）。
- 対象：SM `stop_enclave`、`sbi_sm_stop_enclave`、Eyrie `sbi_stop_enclave`。
- 根拠：不正requestもSTOPPEDへ変更しcontext_switch_to_host後にUNKNOWN_ERRORを返す。
  helperはこれも切替成功として扱い、SDKは回復不能なエラーとして終了する。
  ホスト復帰のa1は明示設定されず、Eyrieのinline asmもa1出力を宣言していない。
- 由来：取込STOP処理とOpenSBI接続の契約。現上流最新版での再現は未確認。
- 方針：0/1以外は切替前にILLEGAL_ARGUMENTで同じenclaveへ返す。
  2（STOP_EXIT_ENCLAVEという旧定義）もSTOPの有効な要求ではない。終了は3006。
  STOP成功時のホストa1は0。既存のtimer/OCALLフレーム保存方式は維持する。
- 修正：[9b7285ae5](https://github.com/yutaka-ishikawa/public/commit/9b7285ae5)「Complete SBI 3004 STOP validation and real guest verification」。
  hostへのa1を0とし、Eyrie asmのa1入出力も宣言。専用試験は実statusを観測する。
- 検証：SM/OpenSBI trace版、SDK、通常／専用runtimeと全verificationパッケージをbuild。
  sbi-errorsのkernel objectもbuild。通常runtimeから専用hookが除外されることをnmで確認。
- 未確認：対応Linux Image/rootfsと完全なModule.symversがないため、追加試験の実ゲスト実行、
  .koリンクは未実施。timer区間の非同期statusだけでM_TIMERとM_SOFTは区別できず、
  原因特定はSM traceのcauseを確認する。既存全PASS報告を新試験のPASSには流用しない。

- 2026-11-09追記：Sstc共存対応後の現行Linux全verification PASSをユーザーから受領。
  両Sstc profileの実行有無は未明示。実機・競合の網羅成功は含めない。

## KSB-028: QEMUでSstc抑止が適用されない

- 状態：修正済（[e4a736519](https://github.com/yutaka-ishikawa/public/commit/e4a736519)）。対象はOpenSBI generic初期化とK3 timer hooks。
- 根拠：ユーザーログで3004直接yieldは3回成功、timer区間は全3bootで0回。
  QEMU root compatibleはriscv-virtio,qemuだが、Sstc抑止はspacemit,k3等のoverrideのみ。
  同じ構成を実QEMU起動するとBoot HART ISA Extensionsにsstcが残ることを再現。
- 原因：OpenSBIがSstcでstimecmpを設定する一方、SMはmidelegを0にしM_TIMER経路を前提にする。
  enclaveへの切替時にSTIEが無効になり、enclaveのsie操作では委譲されていないbitを有効化できない。
- 由来：本リポジトリのK3/OpenSBI移植。上流Keystoneのバグとはしない。
- 方針：CONFIG_K3_KEYSTONE_SM時、全generic platformで既存のSstc抑止とDT修正を実施。
  QEMUに実機用のearly/final initを強制しない。
- 検証：修正後の実QEMU起動でBoot HARTのsstc非表示を確認。全hartのfeature初期化と
  渡すDTの両方に既存hookを接続。Linux suiteの再実行は未確認。

- 現在の方式：[bff3e8dcb](https://github.com/yutaka-ishikawa/public/commit/bff3e8dcb)で全体抑止の対策を、Linux Sstcを維持する
  [共存方式](keystone-sstc-coexistence.md) に置換。enclaveのTIME要求だけMTIMERへ振り分け、
  RUN/RESUMEで独立期限を設定し、STOP/EXITでhost状態を復元する。
  最小の実SM経路でon/off・host期限復元を確認。Linux全suiteと実機は未確認。

- 2026-11-09追記：Sstc共存対応後の現行Linux全verification PASSをユーザーから受領。
  両Sstc profileの実行有無は未明示。実機・競合の網羅成功は含めない。

## KSB-029: makeselfのpipe短読取りでpayloadを切断

- 状態：修正済（専用readerへ置換、[bb84fa987](https://github.com/yutaka-ishikawa/public/commit/bb84fa987)）。
- 対象：4種類のguest runnerとmakeself生成scriptのMS_dd経路。
- 根拠：追加のoffログではsnapshot対策後もMD5不一致と、MD5成功後のgzip途中終了が発生。
  MS_ddのpipe内ddは短いreadもcount=1に数えるため、指定バイト数の前に終了できる。
  実ddへfragmentを順次渡す試験で、32 readが32KiBではなく3104 bytesで終了することを確認。
- 由来：確認したmakeself生成scriptの読取り契約。SMや乱数backendの失敗ではない。
- 修正：`verifications/extract-package.sh`でsnapshotからpayloadをEOFまで取り出し、
  長さ・MD5・任意SHA256・gzipを検査後、その同じlocal fileをtar展開する。
  checksumを無視せず、不一致は失敗とする。単一gzip payload以外は拒否する。
- 検証：4つのtool regression成功。実packageの内容hash一致を確認。
  新しいLinuxゲストでSstc on/offそれぞれ3 boot全suite＋乱数7ケースを実行し全PASS。
- 限界：元の環境での全ての破損要因を独立に特定した意味ではなく、実ファイルが壊れていれば
  引き続き失敗する。[調査・結果](keystone-verification-off-log-followup.md)。

## KSB-030: enclave trap vectorの4-byte整列不足

- 状態：修正済（[e4a736519](https://github.com/yutaka-ishikawa/public/commit/e4a736519)）。対象はSM trap.Sと最終link。
- 根拠：実firmwareのtrap_vector_enclave=0x33d56（低2bit=2）。mtvecはBASEが4-byte境界、
  低2bitはMODEのため、このアドレスは正しいDirect handlerを指定しない。
  実QEMUでenclave実行中のmtvecは通常OpenSBI handlerの0x1020005f0のまま。
  M_TIMER後にmie.MTIE=0、mcause=interrupt7となり、STOP traceも中断statusも発生しない。
- 由来：本リポジトリの圧縮命令を含むOpenSBIとSMのリンク配置。
  trap.Sのnorvc指定だけではsection先頭の4-byte整列を保証しない。
- 方針：vectorへ.balign 4を指定し、最終firmware ELFのsymbol整列をbuild時に検査する。
- 修正：.balign 4と最終ELF symbolのbuild時検査。修正後vector=0x33d58。
- 検証：実QEMUに既存のSM/Eyrieとnative eappをロードし、調査用S-mode runnerから
  CREATE/RUNを実行。修正前は非同期中断0（F0）。整列修正後はcause=7→STOP→2005 RESUME
  →3006 EXIT→2002 DESTROY成功、中断1（P1）を観測。Linux/driverを使わない調査経路であり、
  9回OCALL・3回timer等を含むLinux専用verificationのPASSではない。
  記録は [timer evidence](../verifications/sbi-3004/evidence/timer-preemption.md)。

- 2026-11-09追記：Sstc共存対応後の現行Linux全verification PASSをユーザーから受領。
  両Sstc profileの実行有無は未明示。実機・競合の網羅成功は含めない。

## 以前の構成未指定のユーザー検証報告（2026-11-09）

Sstc共存実装 `bff3e8dcb` の対応後、現行verification全PASSとのユーザー報告を受領。
KSB-027／028／030に関連するSTOP・timer共存の現行Linux suiteについて、
従来の実行待ちをユーザー成功確認済みへ更新する。
KSB-029のchecksum不一致も現行試験での再発報告はないが、根本原因は未確定のため
この時点では要確認の分類を維持した。後続ログと短読取り修正はKSB-029／031に記録する。
今回の報告にはコマンド／ログ添付がなく、Sstc on/off両profileの実行有無は未明示。
実機・競合の網羅試験やクラウド側での独立再実行の成功へは広げない。

## KSB-031: Sstc offのLinux統合試験で中断不足

- 状態：過去原因のみ要確認。`bb84fa987`対応後の再実行はユーザー全PASS確認済み。
  当初の添付log.txtは明示的な `--all --sstc off`。
- 観測：qemu-dev 2 bootはarmed区間43回、cancel区間0回（exit20）。
  unavailableはarmed区間0回（exit18）。後続crypto/edgecallは未到達。
- 別件：乱数zkrとzkr-absentは展開時のgzip途中終了／MD5不一致で、SBI実行前に失敗。
- 過去の原因：未確定。現行ではクラウドとユーザー環境の双方で全PASS。
  最小S-mode runnerのoff成功だけをLinux経路の成功へ広げない。
- 対応：選択BINの共存実装文字列を事前検査し、不一致時にpath/SHA256と再build案内を表示。
  bootのtimer情報を表示し、事前検査失敗時に古いserialログを再表示しない。
- 検証：新しいLinux環境でon/offの3 boot全suite＋乱数7ケース、さらに通常trace=0版で
  on/off全suiteがPASS。SM timerコードは今回変更していない。元の環境の失敗は再現せず。
- 未確認：提供された環境のboot情報・artifact hashとの一致。古いfirmwareが原因と
  断定せず、履歴の要確認を維持する。現行の実行失敗・作業阻害項目にはしない。[調査・結果](keystone-verification-off-log-followup.md)。
- 検証範囲：前回の構成未指定の全PASS申告は履歴として維持するが、今回の明示off失敗を含む成功とはしない。

- 2026-11-09追加：直前に案内したoff再確認手順に対し、ユーザーから全PASSを受領。
  新しいログ・manifestは未添付で、過去の原因が証明された意味ではない。

## 今後の必須更新手順

新たに同様の不具合を発見したら、修正前でも本書へ登録する。
連番を末尾へ追加し、既存IDは変更・再利用しない。調査途中なら未確認事項を明示する。
修正時はそのIDの状態、修正コミット、検証結果と残る未確認範囲を更新する。
ユーザーから結果を受領した場合も、報告範囲を超えてPASSを広げず追記する。

再利用する記入様式:

```markdown
## KSB-NNN: 短い題名

- 登録日・最終更新日：YYYY-MM-DD（日本時間）
- 状態：未修正／修正済／要確認
- 対象：component、source、影響版またはcommit
- 由来：取込コード／上流比較済（commit指定）／移植／build環境／未確認
- 症状・再現条件：実行手順、必要な設定
- 原因・影響：確認できた事実と推測を分ける
- 根拠：ログ、機械語、source差分、関連報告
- 修正：方針と実際のcommit。未修正なら予定・対応計画
- 検証：build／バイナリ検査／実QEMU／実機／ユーザー報告を区別
- 未確認：未実施の条件・残る制約
```

秘密鍵やsealing keyを報告書へ掲載しない。既存の累積変更記録と個別解析文書は根拠として
リンクし、本書を不具合ID・現在の状態を確認する入口にする。

## KSB-032: multimem有効化時の重複定義と未定義callの成功扱い

対象：SM plugins.c / multimem.c。元コードはplugins.cからmultimem.cをincludeし、
K3ビルドは同じファイルも別途コンパイルする。有効化するとdo_sbi_multimemが重複し
linkに失敗することを確認した。また未知callが0（成功）を返し、4000のhost文脈を
明示的に拒否していなかった。K3のbuild統合と既存pluginのエラー処理に関する問題で、
他の上流build全体にlink失敗を帰属させない。header includeへ修正し、未知callと
host呼出しを拒否する。4000のcopy先もprivate EPM内に限定する。
状態：修正済み。Sstc on/offの実QEMU試験で異常要求拒否・失敗後close・反復回収を確認。
修正commit：[2f87a9d57](https://github.com/yutaka-ishikawa/public/commit/2f87a9d5736d7653c512e050e944f17b787098e5)。証跡は[FID 4000検証記録](../verifications/sbi-4000/results.md)。

## KSB-033: FINALIZE失敗後のdriver IDRに解放済みポインタが残る

対象：linux-keystone-driver/keystone-ioctl.c。FINALIZEのSM CREATE失敗時に
destroy_enclave()だけでメモリを解放し、IDRとfileのUIDを残す実ソースを確認。
その後SDKのdestroy()/closeが同じポインタを参照する。backing CREATE失敗の
rollback実装中に発見した既存driverの欠陥。上流releaseでの再現範囲は未確認。
失敗時は所有権を保持して明示DESTROY/closeで一度だけ回収するよう変更する。
関連して新backing操作はfile所有者検査・fileごとのmutexで状態遷移を直列化する。
状態：修正済み。Sstc on/offの実QEMU試験で異常要求拒否・失敗後close・反復回収を確認。
修正commit：[2f87a9d57](https://github.com/yutaka-ishikawa/public/commit/2f87a9d5736d7653c512e050e944f17b787098e5)。証跡は[FID 4000検証記録](../verifications/sbi-4000/results.md)。

## KSB-034: 新規backing実装のhost復帰時PMP解除不足

本作業中の未公開草稿に限定。新しいREGION_BACKINGをEPMと同様にhost復帰時
NO_PERMへ変更すると、host-visibleという設計に反してhostからも参照不能になる。
QEMUの生成・破棄反復で解放済みbackingページをLinuxが再利用しclear_pageの
store access faultとなる実ログで確認。上流Keystoneの不具合ではない。
host復帰・RUN失敗rollbackではbackingのPMPをOFFにし、OS catch-allへ戻す。
DESTROYでも全hartの解除完了後にdescriptorを解放する。
修正commit：[2f87a9d57](https://github.com/yutaka-ishikawa/public/commit/2f87a9d5736d7653c512e050e944f17b787098e5)。
状態：修正済み。Sstc両profileで2 enclaveの反復破棄、CPU切替、
256 MiB + 4 KiB CMA/TOR backingの解除・回収を確認。証跡はFID 4000検証記録を参照。

## KSB-035: SDKのdevice fd・hostオブジェクトの解放不足

対象：SDK host/Enclave.cpp、KeystoneDevice.cpp、KeystoneDevice.hpp。ソース確認で
Enclaveのdestructorはdestroy()だけを呼び、destroy()はpDevice->destroy()だけを呼ぶ。
KeystoneDevice::destroy()はSM enclaveを破棄するがdevice fdをcloseせず、
KeystoneDeviceのdestructorも空である。host側のdevice/memoryオブジェクト等の
ライフサイクル整理が別途必要。FD数やhost heapの反復増加量の実測は未実施。
影響は長寿命hostプロセスでの資源増加。今回のbacking_bytes回復はdriverが所有する
backingページの回収を検証するものであり、SDKの全資源解放の証明にはしない。
既存SDKに確認した問題で、上流releaseごとの影響範囲は未調査。今回は未修正。

## KSB-036: untrustedサンプルのcount未初期化

`keystone/examples/tests/untrusted/untrusted.c`は`int ct;`のまま文字数計算で`ct++`する。
ソースで確認した既存サンプルの未定義動作。samples側は0初期化し、mallocと共有コピーも検査する。
上流ディレクトリは比較用に保持し変更しない。修正後のguest結果を本作業記録へ記載する。

## KSB-037: 上流example runnerの失敗が終了statusに反映されない

`keystone/examples/tests/test-runner.cpp`はinit/runのエラーを検査せず、retval不一致も
表示だけで最後は0を返す。CMakeLists.txtは`test-stack/retval`等を探すが実ファイルは
`stack/retval`等で、期待値が指定されない。ソース確認で判明した上流取込サンプルの問題。
attestation/host/verifier.cppにも不一致を表示するだけの経路がある。
samples側は期待値を明示し、SDK status・enclave値・OCALL・DESTROY失敗を非0で返し、
実行スクリプトも失敗で停止する。上流側は比較用として残す。

## KSB-038: fib-benchのrdcycleと継承scounterenの不整合

`examples/tests/fib-bench/fib-bench.c`はU-modeでrdcycleを実行するが、SMの
`clean_smode_csrs()`はLinuxのscounterenを継承する。現K3 QEMU guestではCYが
許可されず、pc=0x103b0、mtval相当=0xc00029f3、scause=2を観測した。
アドレスをsample ELFへ照合してread_cycles()と特定。Keystone全機種共通の欠陥とは
断定せず、counterアクセス方針との適合問題として分類する。samples側は許可済みの
rdtimeでtimebase tickを計測し、cyclesという表示をしない。SMのcounter権限は変更しない。

## KSB-039: 新規共通sample runnerのLinux syscall配送漏れ

本作業の未公開草稿に限定。nativeの1〜4番OCALLだけを配送し、glibc helloの
EDGECALL_SYSCALLを拒否していた。guestではSDK=0 exit=0でもrunnerが失敗と判定。
既存SDKのincoming_call_dispatchへsyscall OCALLを渡すよう修正した。
上流の不具合ではない。修正後、全12アプリがSstc on/off両方でPASSした。

## KSB-040: attestorサンプル自身のreport転送長と失敗処理

`examples/attestation/eapp/attestor.c`はnonce上限を2048とし、attest_enclaveの結果を
確認せず2048-byte buffer全体をOCALLする。正規reportは1352 bytesなので、
余分な696 bytesも送る。Eyrieが2048 bytes書いていたKSB-002とは別の層の問題。
samples版では上限1024、checked API、sizeof共通report型、成功時だけOCALLへ変更した。
上流ソースは比較用に保持し、変更していない。鍵・SM hashの旧前提は別途
[互換性記録](keystone-examples-integration.md)にまとめた。

### samples統合の最終検証（KSB-036〜040）

[検証記録](../samples/results.md)に示すとおり、Sstc on/offの実QEMUで
全12アプリを確認した。--basicでは暗号例をSKIPとして区別した。
誤retval、誤った外部device pin、unavailable providerの完全実行は非0となる。
KSB-036/037/040はsamplesコピー側の修正で、元のkeystone/examplesは変更していない。
KSB-038はcounterアクセス方針への適合、KSB-039は本作業の草稿に限定した不具合。
修正commit：[8d8fd5b9c](https://github.com/yutaka-ishikawa/public/commit/8d8fd5b9c8e52f54169064548dad074e20ac5186)。元のexamplesは保持したままで、変更対象はsamples統合側。

## KSB-041: attestor統合時のループ削除による動作範囲の減少

samples統合時に、元attestorの1〜10000のループと5000/10000での値OCALLを削除した。
互換性修正に必要な削除ではなく、追加2回のhost復帰/RESUMEと、nonceコピー前の
処理経路を失っていた。上流の不具合ではなく本リポジトリの統合作業による後退。
ユーザー指摘を受けて、GET_STRING → ループ/2 OCALL → nonceコピー → attestの順で復元。
OCALL失敗時の非0終了は維持する。時間計測は元にもなく、最適化後の命令数や一定負荷を
保証するループとは扱わない。Sstc on/offで5000/10000の出力が正確に2回あり、その後のreport検証と全sample成功を確認。
証跡は[samples/evidence/loop-restored.json](../samples/evidence/loop-restored.json)。

復元・差分評価のcommit：[715228dcf](https://github.com/yutaka-ishikawa/public/commit/715228dcf7ca4aeb3b1694fb4e69f58dde4cab74)。


## KSB-042: EXIT済みenclaveをRESUMEすると再進入する

新C検証 `A-2005-02/after-exit` で再現。`enclave.c:exit_enclave()` は
`n_thread` を0にして状態をSTOPPEDとする。一方 `resume_enclave()` は
STOPPEDかつ `n_thread < MAX_ENCL_THREADS` を受理するため、EXIT済みcontextも
再開可能と判定する。EXIT後のRUNはNOT_FRESHとなるが、RESUMEはNOT_RESUMABLEに
ならず、実QEMUで `[runtime] page fault ... scause: 0xd` に到達した。
これは新C clientがSMを模擬した結果ではなく、production driver→実SM/Eyrieでの再現。
原版との差分照合前なので上流由来とは断定しない。通常のEXIT→DESTROYだけの
既存試験では検出されなかった。
再現手順・採用成果物hashは [robustness](../verifications/robustness/README.md) と
同ディレクトリのevidenceに記録する。新試験はこの挙動をFAILのまま扱う。

- KSB-084修正後の16 hart同居QEMUでも `robustness --lifecycle-only` の
  `A-2005-02/after-exit` が失敗し、RESUMEでEyrieのpage faultを再確認した。
- ホストのコンテキストとPMPポリシーの復元後に、終了したEnclaveをEXITEDにする。
  DESTROYはEXITEDも回収対象とする。16 hart同居QEMUで
  `A-2005-02/after-exit`、ライフサイクル・リソース寿命、STOP/RESUME、
  edgecall 2 MiB・256 MiBが成功した。

## KSB-043: 並行CREATE/DESTROYのPMP admission競合で回収不能

別file・別CPUのC workerによるCREATE→RUN→OCALL/RESUME→EXIT→DESTROYを
並行実行すると `pmp_unset_global:HSM Start in progress`、SBI error 100003、
次回DESTROY 100005を実QEMUで観測した。`ipi.c` のHSM/PMP admissionは
`k3_hsm_gate_acquire()` と `k3_policy_lock()` の非待機try-lockで競合を拒否する。
`pmp_unset_global()` はこれをPMP失敗にするが、`destroy_enclave()` は既に
DESTROYINGを公開しているため、その後の通常DESTROYでは回収できない。
競合相手がHSM Startだったとログだけで断定できない。PMP更新同士でも同じgateを使う。
K3移植固有のadmission経路。driverは保護不明のページをquarantineしており、
テストの都合で再利用させてはならない。未修正。安全な更新直列化と、更新前の
一時拒否／部分更新後の失敗を区別した状態遷移・rollbackの設計が必要。
初回失敗ログと最終再現はrobustness evidenceに保存する。

## KSB-044: CREATE失敗cleanupが全hartの保護解除を確認しない

`enclave.c:create_enclave_internal()` の失敗経路で、
`pmp_set_global()` 失敗時は `free_shared_region` へ進み、
`unset_region` からの `pmp_unset_global(region)` の結果も検査しない。
その後にPMP descriptorとEIDを解放する。全hart更新は途中失敗し得るため、
更新前拒否と部分適用後の失敗を同一cleanupで扱うと保護状態との整合を保証できない。
戻り値無視と経路はソースで確認したが、部分適用を注入した実QEMU再現は未実施。
上流にも同等問題があるかは未照合。未修正。F-PMP/F-IPIの詳細試験を増やす前に、
解除確認不能時のdescriptor/EID/物理ページの保持契約を確定する必要がある。

## KSB-045: MPXY共有メモリーのサイズ丸めがpage数になる

- **確認日・対象**：2026-11-11、基準 `8ce25d283e19c02cdf2e08727460473b8408882a` の
  [sbi_mpxy_register_channel](../opensbi/lib/sbi/sbi_mpxy.c)。
- **条件・ソース証拠**：`msg_data_maxlen` が現在の `mpxy_shmem_size` を超えると、
  `(maxlen + PAGE_SIZE - 1) / PAGE_SIZE` をサイズ変数に格納する。
  この値はpage数だが、利用側はbytesとして扱う。PAGE_SIZE=4096なら4097 bytesが2になる。
  既存OPTEEDはmaxlen=PAGE_SIZEであり、そのchannelだけでこの分岐の発火を確認したわけではない。
- **由来**：OpenSBI取込コード。上流の
  [2de7dfb6813facba8e376897290bedb18ef38401](https://github.com/riscv-software-src/opensbi/commit/2de7dfb6813facba8e376897290bedb18ef38401)
  は同じ箇所をbyte単位のROUNDUPへ修正する。Keystone固有の新規バグとは分類しない。
- **影響**：大きなchannel登録時に共有領域サイズの通知・転送境界の契約が崩れる。
  実際のサービス障害・メモリー破壊・漏出は今回再現しておらず、断定しない。
- **状態・方針**：`d32afa86c` で上流修正をバックポートした。既存のmapping変更を維持した。
  [取り込み計画P1/T-MPXY](optee-opensbi-keystone-merge-plan.md)に実ゲストでの確認条件を記載。
- **検証範囲**：K3 Keystone構成でOpenSBI＋SMをビルド・リンクした。
  PAGE_SIZE超channelの実ゲストECALLと実機検証は未実施。

## KSB-046〜056: OpenSBI上流差分調査で確認した修正対象

確認日：2026-11-11。基準は本repo `779fb85a764e678a3c9bbbac1450e4c434cb319d`。
以下は上流patchと現行の未修正条件のソース照合であり、実ゲスト再現・悪用の実証ではない。
全件とも今回の変更では機能修正をしていない。上流起因の共通コードとK3固有の統合を区別する。
計画・採否・依存・試験は[OpenSBI差分](opensbi-upstream-delta-2026-11-11.md)と
[バックポート全件台帳](opensbi-upstream-backport-catalog.md)へ対応付ける。

### KSB-046: MPXY属性範囲endpointのoverflow

- 対象：`opensbi/lib/sbi/sbi_mpxy.c` のread/write attrs。
- 条件・証拠：`u32 end_id` に `base_attr_id + attr_count - 1` を格納する。
  endpointがwrapすると上限検査をすり抜け得る。driver側の属性配列アクセスへ影響する。
- 上流修正：`2afa77759241d425a6130e6a52560ef6fa2a6dac`。endpointをu64化する。
- 状態：未修正。BP01/T-MPXYで境界正常入力、不正入力、driver未到達を確認する。

### KSB-047: PMU counter index検査のoverflow

- 対象：`opensbi/lib/sbi/sbi_pmu.c:pmu_ctr_idx_validate()` とSKIP_MATCH経路。
- 条件・証拠：`cbase + sbi_fls(cmask) < total_ctrs` に加算overflow検査がなく、
  巨大なcbaseがwrapして有効と判定され得る。counter配列/CSR選択の範囲保証を損なう。
- 上流修正：`0dfe6be08778102bf2fde61c5c99ea2cceb0b73a`。
- 状態：未修正。BP02/T-PMUでULONG_MAX境界、zero mask、SKIP_MATCHを実ECALLで確認する。

### KSB-048: PMU event infoサイズの乗算overflow

- 対象：`opensbi/lib/sbi/sbi_pmu.c:sbi_pmu_event_get_info()`。
- 条件・証拠：検査前に `num_events * sizeof(struct sbi_pmu_event_info)` を計算する。
  wrapした小さい値でdomain/mapping検査をしてから元のcountで参照する懸念がある。
  現行のdomain検査強化だけでこの乗算を修正したことにはならない。
- 上流修正：`f45b9433ed03588edf7c5a9a803c67b2c9d09aee`（完全SHAは全件台帳）。乗算前上限検査等を移植する。
- 状態：未修正。BP02/T-PMU。map/unmap失敗処理を保持し、ゼロ/巨大countと正常countを確認。

### KSB-049: DBTR範囲のoverflowと正当な終端範囲の拒否

- 対象：`opensbi/lib/sbi/sbi_dbtr.c` のREAD/UPDATE/INSTALL。
- 条件・証拠：READの `trig_idx_base + trig_count >= total_trigs` は加算overflowに弱く、
  最終要素1件などexact-endの正当な範囲も拒否する。UPDATEにもcount境界条件が残る。
- 上流修正：`a14e4d24a1f51a9d6d263f1da4e23c01bd89f3ce`と後続`ed70256dd22c09962d146e433834239825ef0616`。片方だけで完了としない。
- 状態：未修正。BP03/T-DBTRで0/1/N triggerと巨大count、exact-endを実guest確認する。

### KSB-050: RPMI共有queueの容量検査不足

- 対象：`opensbi/lib/utils/mailbox/fdt_mailbox_rpmi_shmem.c` のtransport初期化。
- 条件・証拠：DTのreg_sizeからheader分を減算してslot数を算出する前に、最小容量・
  実用的なring長・u32表現上限を検査しない。小さいDT領域でunderflow/div0等の条件を作り得る。
- 上流修正：`95c7980851171ef7b0fd909214ec5838f34ee12d`。
- 状態：未修正。BP04/T-RPMI。専用DTの小容量拒否と正常server通信を確認する。

### KSB-051: RPMI queue indexのoff-by-one

- 対象：同transportの `smq_rx()/smq_tx()`。
- 条件・証拠：`mctl->queue_count < queue_id` は `queue_id == queue_count` を受理する。
  DTにないqueue contextを選択し得る。
- 上流修正：`9bc841226d8a63aaa59fc6b26a4452fe548c6589`。両方向で `queue_id >= queue_count` を拒否する。
- 状態：未修正。BP04/T-RPMI。専用検証firmwareの実transportで境界と正常queueを確認する。

### KSB-052: SBI/ISA拡張名文字列の容量境界

- 対象：`opensbi/lib/sbi/sbi_ecall.c:sbi_ecall_get_extensions_str()` と
  `opensbi/lib/sbi/sbi_hart.c:sbi_hart_get_extensions_str()`。
- 条件・証拠：各拡張名の本来の長さでoffsetを加算し、容量によって止めない。
  最後の `exts_str[offset - 1]` も容量外になり得る。発火は登録拡張列とbuffer長に依存する。
- 上流修正：ISA列は`d2166a9d4045013654b04a1a46ab43fdb7dabb95`、
  SBI列は`f95648d3955d72f77e13315a990a6135303978a5`。
  同じ関数への連続patchではない。両方の容量境界を個別に直す。
- 状態：未修正。BP05/07、T-CORE/T-CSR。実firmwareの長い拡張列でguard/終端と起動を確認。

### KSB-053: HSM拒否前のscratch書換え

- 対象：`opensbi/lib/sbi/sbi_hsm.c:sbi_hsm_hart_start()`。
- 条件・証拠：STOPPED状態確認より先に `next_arg1/next_addr/next_mode` を書く。
  不正状態へのstartが後で拒否されても起動contextは変更済みとなる。
- 由来：上流共通処理の修正`131bda944704293fa75295060aec96061cdb3749`に対応。ただし現行にはK3 PMP admissionが挿入されており、
  patchを丸ごと置換せずbegin/cancel/finish契約を維持する。
- 状態：未修正。BP06/T-HSM。実guestで拒否後のscratch、並行start、warm bootを確認する。

### KSB-054: domain subset判定のXLEN shift

- 対象：`opensbi/lib/sbi/sbi_domain.c:is_region_subset()`。
- 条件・証拠：`BIT(reg->order)` は `order == __riscv_xlen` の全域regionで幅以上のshiftになる。
  Cの未定義動作により包含判定が保証できない。
- 上流修正：`3baca10015393359ec46a2500c8ebe7daa9672c6`。現上流の修正pathはheaderだが、旧pathへ同じ対策を移植する。
- 状態：未修正。BP08/T-PMP。全域region、被覆/隣接/単一region、PMP保護を実firmware確認。

### KSB-055: RPMI CPPC要求field順序の互換性

- 対象：`opensbi/include/sbi_utils/mailbox/rpmi_msgprot.h` のCPPC PROBE/READ/WRITE要求。
- 条件・証拠：現行構造体はhart_id→reg_idの順。上流修正`332798211e7232da60158b0545b23c61b5338516`は仕様に合わせreg_id→hart_idとする。
- 影響：仕様準拠serverとの通信に影響する。一方K3側serverも旧順を使う場合は、OpenSBIだけを
  修正すると既存通信を壊す。今回K3 serverの実装/実通信は照合できていない。
- 分類：現行wire ABIが上流修正前であることは確認済み、K3上の実障害は未確認の互換性制約。
- 状態：BP04/T-RPMIの修正候補。server側と必要なら同時更新し、実機probe/read/writeを確認する。


### KSB-056: PMU FW counter探索失敗後の配列書込み

- 対象：`opensbi/lib/sbi/sbi_pmu.c:sbi_pmu_ctr_cfg_match()`。
- 条件・証拠：`pmu_ctr_find_fw()` の結果に対する `ctr_idx < 0` 検査より先に、
  FW_PLATFORM eventで `fw_counters_data[ctr_idx - num_hw_ctrs]` へ書く。
  探索が失敗する入力・資源状態で負のindexによるM-mode状態破壊の懸念がある。
- 上流修正：`ac16c6b6`（完全SHAは全件台帳）。現行にないhw_counters_data変更部分は機械的に追加せず、
  現行の探索結果と配列所有関係に合わせて移植する。
- 状態：未修正、ソース照合のみ。BP02/T-PMUでFW counter枯渇・unsupported eventと正常割当を確認する。


### KSB-057: RAM FIT作成が共通ESOS構成・LZOを扱えない

- 登録日：2026-11-20。対象：scripts/build-jupiter2-ram-boot-image.py。
- 条件・証拠：ユーザー提供の2026-04-30版ESOSのdumpimage一覧は、
  DescriptionがESOS Dual Core Configurationのconf_dual一つに27個のloadablesを持ち、
  LZO圧縮imageを含む。加えて販売元SPLのboard_fit_image_post_process等は
  rcpu0-fw／rcpu1-fw／rcpu-data-null等のimage名で分岐するが、従来packagerは名前をesos-Nへ変更していた。従来コードはU-Bootのk3-pico-itxとDescriptionが一致する
  ESOS構成を必須とし、さらに非圧縮以外を拒否するため生成に失敗する。
- 由来：本リポジトリで作成したRAM起動用packagerの入力形式対応不足。
  Keystone本体や販売元ESOSの欠陥とは扱わない。
- 影響：販売元ファイルを用いた統合FITを作れない。単に圧縮を許可すると、圧縮後の
  ファイル長による配置検査では展開後の重複を見逃すため、サイズ検査も同時に修正する。
- 修正：本項追加と同一コミットで--esos-configurationによる独立した明示選択を追加。
  全loadablesの元のimage名・順序・圧縮データを保持し、lzopで求めた展開後サイズで重複を検査する。
  image名を使うhookは公開SPLソースで確認したが、使用中の4月版FSBLバイナリーとの照合は未実施。
  構成選択と展開サイズをmanifestに記録する。省略時のボード一致検査は維持する。
- 検証：実mkimage／dumpimage／dtc／lzopを用い、27 loadablesとLZO・非圧縮混在の
  FIT生成、格納データ一致、構成指定、展開後の重複拒否を含むホスト試験を実施。
  入力は再現用fixtureで、ユーザー実ESOSバイナリー自体は未入手。
  Jupiter2実機起動・ESOS初期化・QEMU integration PASSは未確認。


### KSB-058: Jupiter2の小領域が実機PMP粒度で表現できず起動停止

- 登録日：2026-11-21。対象：K3のdomain登録とopensbi/lib/sbi/sbi_hart.cのKeystone用PMP設定。
- 条件・証拠：ユーザーのJupiter2実機UARTでOpenSBI v1.6、SM/TIMER初期化後、
  base=0xcac90c00、order=8、flags=0x80000003の領域をgran=12で表現できず、
  init_coldboot: PMP configure failed (error -2)で停止した。
- 影響：OpenSBI＋SMへ到達するが、U-Boot・Linuxへ移行できない。
- 由来：販売元domainの小領域登録と、本リポジトリのK3 Keystoneの厳密な表現可能性検査の
  組合せによる移植・統合問題。上流Keystone本体の欠陥とは扱わない。
- 登録元：RPMI mailbox transportのdb-reg登録。公開K3 DTの0xcac90c00／0x100と一致。
- 修正候補：K3＋SM構成のこの既知doorbellだけを4 KiBのM-onlyページとして登録する。
  queue・doorbellの実アドレスは維持し、汎用PMP検査は変更しない。
  明示S/U grant、引渡しDTの有効な直接mailboxとの競合は拒否する。
- 互換性制約：包含ページにはmailbox0〜3があり、元の小窓の外3840 bytesもS/U禁止となる。
  別途ロードするLinux DTを検査・修正したものではない。直接mailbox利用を継続する構成では
  そのままLinux起動へ進めず、所有契約・SBI経由化／配置変更を別途確認する。
- 検証：SMありのK3 audit構成とSMなしk3_defconfigの実クロスリンク成功、
  RISC-V ELF・SMシンボル・mtvec整列を確認。模擬PMPテストは追加していない。
  実機でのPMP成功、U-Boot／Linux／Enclave到達、実QEMU integration PASSは未検証。
- 修正履歴：候補実装は[995c9c1ad9b765ed9a66c1186f96023f1a3779ad](https://github.com/yutaka-ishikawa/public/commit/995c9c1ad9b765ed9a66c1186f96023f1a3779ad)。初回の実機失敗記録と
  調査計画のコミットは384e4b1e2cc6f14de313f6138617417a47b1c7b4。
- 2026-11-21実機再試験：K3-RPMIのpage登録とorder=12を確認し、粒度拒否は解消。
  続くslot計画でKSB-059が発生した。PMP全体や次段起動の成功とは区別する。
- 詳細・検証計画：[Jupiter2 PMP粒度問題](jupiter2-pmp-granularity-issue.md)。



### KSB-059: 実機domain領域数がKeystoneのPMP割当上限を超える

- 登録日：2026-11-21。対象：opensbi/include/sbi/k3_keystone_boot_slots.h、
  opensbi/lib/sbi/sbi_hart.cのK3 root配置、keystone/sm/src/pmp.cのboot admission。
- 証拠：KSB-058修正後の実機ログでorder=12のRPMI領域を通過し、
  REJECT root PMP capacity/order regular=13 broad=1 count=16で停止した。
- 条件・影響：rootの13個＋fallback一つで14個を使用するため、Keystoneには2個しか残らない。
  OpenSBI側のslot計画とSM側のadmissionはいずれも最低3個を要求し、次段へ進めない。
- 分類・由来：K3実機のdomain構成と現行16-PMP割当契約の不整合・移植制約。
  拒否自体は設計どおりであり、上流Keystoneの欠陥やPMP検出不良と断定しない。
- 修正候補：同じfw_startから始まる隣接したRXと包含RW領域に限り、flags・実行時サイズ・
  legacy policyを確認し、同じS/U禁止を一つのハードウェアentryで表す。domain記録は残す。
  canonical配置を計画・書込み・全CSR readback・admissionで共有し、最低3個は維持する。
  今回はOpenSBI用13個、Keystone用3個の予算。一般的なEnclave機能や同時実行数の保証ではない。
- 後続の実機UART追記：root13個・Keystone空き3個の配置とreadback、X100全8 HartのSM初期化、U-BootとLinux起動を確認。A100は別件KSB-071で停止し、Enclave成功は未確認。初回の拒否記録の詳細：[PMP実機再試験結果](jupiter2-pmp-granularity-issue.md#7-修正後の実機結果粒度を通過しpmp容量で停止ksb-059)。


### KSB-060: 正規rootのロック付き保護とboot preflightが不整合

- 登録日：2026-11-21。対象：opensbi/include/sbi/k3_a1_csr_preflight.h、
  opensbi/lib/sbi/sbi_init.cのpost-PMP gate、K3 root PMP設定。
- 証拠：KSB-059の実機domainにはENF_PERMISSIONS付きのRCPU予約領域が4個あり、
  PMPへはL付きdenyとして登録する。一方k3_a1_preflight_localはfallback前のLを一律拒否する。
- 影響：容量問題を解消してPMP設定・readbackを通過しても、その次のadmissionで拒否される条件がある。
  この停止位置はまだ実機で観測しておらず、ソース上の契約不整合として登録する。
- 由来：本リポジトリのK3用root配置と、QEMU中心の厳格なpreflightの組合せ。
  上流Keystone自体の不具合とは断定しない。
- 方針：Lを消さず、汎用preflightの既定の拒否も維持する。実rootの全entry・fallback・
  未使用slotをreadbackで照合して得た正規ロックmaskだけを、K3起動経路で明示的に認める。
  不明なL、free slotやfallbackのL、不一致は引き続き拒否する。
- 修正候補：domain由来の全entry・fallback・free slotを実CSRで再検証して得たlock maskのみ、
  専用preflight経路へ渡す。既定preflightはLを許可しないまま。未知のlock・不一致は拒否。
  後続の実機UARTでX100全8 Hartがroot readbackとSM初期化まで通過した。A100は別件KSB-071で停止。


### KSB-061: 共有bottom PMP slotの解放が残るOS／UTM予約を失う

- 登録日：2026-11-21。対象：keystone/sm/src/pmp.cのpmp_region_free_atomic()。
- 証拠：NAPOTのPMP_PRI_BOTTOMはslotを複数regionで共有でき、K3のOS-wide regionと
  各EnclaveのUTMは同じ末尾slotを使う。一方freeは一つのregionを解放するときに、
  同じslotを参照する他のregionを確認せずreg_bitmapを消す。
- 影響：UTMのDESTROY等の後もOS-wide regionが残るのに、ANY割当がそのslotを空きと判断する。
  少数slotでCREATE／DESTROYを繰り返す経路や複数Enclaveの資源管理に影響し得る。
- 由来：本リポジトリで取り込んだPMP allocatorの参照管理の不足。上流最新版との一致は未確認。
- 修正候補：pmp_lock下で、解放するregionの定義を外した後に残存regionを走査し、
  同じslot（TORの下端slotも含む）への参照がなくなった場合だけ予約bitを消す。
  実機での当該破綻と修正後のCREATE／DESTROY反復は未再現・未検証。


### KSB-062: K3でOS-wide denyとUTMのslot共用が後段fallbackと両立しない

- 登録日：2026-11-21。対象：keystone/sm/src/enclave.cのCREATEとswitch_to_enclave()、
  sm.cのosm_init()、K3 root fallbackの配置。
- 証拠：OS-wide regionとUTMはPMP_PRI_BOTTOMで同一のKeystone末尾slotへ割当てる。
  切替ではosm_pmp_set(PMP_NO_PERM)の後にUTMを許可するため、同slotの全域denyがUTM窓へ置換される。
  K3にはその後ろにroot-owned全域S/U allow（index15）が残り、UTM外の通常OSメモリーも許可され得る。
- 分類・影響：本リポジトリのK3統合の保護契約不整合。実機で攻撃を実行した証拠はなく、
  ソース上のslot aliasとfirst-match規則から確認した。既存rootの明示的MMIO grantとは別の問題。
- 方針：K3のUTMはOS-wide denyより前の独立したKeystone-owned slotへ割当てる。
  必要数がない場合はCREATEを拒否する。root fallbackの所有を奪ったり、最低数を下げたりしない。
- 資源計算：K3ではOS用1＋UTM用1＋EPM用1以上が必要。残り3個ならNAPOT EPM一つの最小構成で、
  TOR EPM、backing、複数Enclaveにはさらにentryが必要。先の共有前提の上限計算は訂正する。
- 修正候補：K3に限りUTMをPMP_PRI_ANYへ変更し、OS-wide denyとは別の前段slotを予約する。
  entry不足は既存のCREATE rollbackへ戻す。non-K3のUTM方針とroot-owned fallbackは変更しない。
  実機のOSメモリー保護・複数Hart・Enclave実行は未検証。

KSB-059〜062の候補実装：[4f976074681bd1377de9af961ea0ab70a3670984](https://github.com/yutaka-ishikawa/public/commit/4f976074681bd1377de9af961ea0ab70a3670984)。SM 30単位の実クロスコンパイルと
SMあり／なしのOpenSBIリンク、mtvec整列を確認。実QEMU・実機試験は未実施で、
ビルド成功を保護成功と扱わない。詳細：[資源計算と候補実装](jupiter2-pmp-granularity-issue.md#8-ksb-059060061062の修正候補とenclave数の制約)。



### KSB-063: RAM起動後のU-BootでUFS通信が失敗

- 登録日：2026-11-21。条件：開発版RAM起動の検証中、U-Boot UARTでscsi scanを実行。
- ユーザー実機証拠：UFS power mode変更がtimeoutし、一度gear3／lane2の設定表示後、
  Error in status:00000004、query descriptor opcode=0x01／idn=2の失敗、
  Timedout waiting for UTP response、err=-110が反復した。
- 解釈：公開販売元U-Bootのdrivers/ufs/ufs.hでUIC_ERROR=0x4。
  リンク／通信エラーが観測され、UFSからbootファイルを読む段階に進めていない。
- 分類：実機の統合障害として記録するが、媒体故障、PMP起因、OpenSBI／SMの欠陥とは断定しない。
  その後、ユーザーから販売元OpenSBI入り統合FITと、元の販売元FSBL＋u-boot.itbでも
  同様のdescriptor失敗が報告された。Keystone固有とする根拠はない。
  各試行の完全な起動ログ・入力SHA、通常起動での比較結果は引き続き必要。
- 方針：scsi scanの反復やflashで修復しようとせず、他媒体の列挙と、完全電源断からのA/B比較を行う。
  FSBL／U-Boot／DTB／ESOSは同じ入力を使い、OpenSBIだけを販売元版へ差し替える。
  両者で失敗ならRAM起動経路やUFS初期化条件、販売元版だけ成功なら開発版との差分へ絞る。
- 状態：未修正・原因調査中。詳細：[UFS起動媒体の確認](jupiter2-pmp-granularity-issue.md#9-ram起動後のufs通信失敗ksb-063)。
  次の比較候補は[参照FSBL/ESOSの開発手順](jupiter2-reference-ram-boot-development.md)。

### KSB-064: 参照ESOS結合とconf_dualのdescription不一致

- 登録日：2026-11-21。対象はganboing/u-boot-k3の固定コミット
  4c294a06c14e46e9c9cc934373c3e63919703017、scripts/combine-esos.shを今回のESOSへ適用する場合。
- 出典・証拠：参照ソースはdescriptionをキーとして構成を結合する。
  ユーザー提供dumpimage一覧はconf_dual、description=ESOS Dual Core Configuration。
  conf_11のdescription=k3-pico-itxと一致しない。
- 影響：imagesのコピーだけが行われ、対象構成のloadablesにESOSが追加されない可能性がある。
  これは入力組合せから確認した統合上の制約であり、参照記事の使用ESOSでも起きると主張しない。
  また現在の実機UFS障害の原因だとは断定しない。既存packagerは既にconf_dualを明示選択できる。
- 回避：新しい参照ビルダーも既存packagerの明示選択を使用し、元の名前・全loadables・順序を維持する。
  参照側combine-esos.shは呼び出さない。組込みOpenSBIのバイト一致も検査する。
- 検証：実dtc/mkimage/dumpimage/lzopを使う参照FIT＋27 loadablesのホスト回帰試験を追加。
  実ESOSのバイナリー検証、ESOS開始とUFS列挙の実機確認は未実施。

### KSB-065: 参照FSBLのESOS開始失敗とRAM起動時のエラー処理

- 登録日：2026-11-21。ユーザー実機ログはSPL 2022.10-g4c294a06-dirty、
  Nov 21 2026 11:56:38 +0900。DDR training 5623ms、memory verify pass、
  2191805 bytesのFIT転送後、k3-pico-itx選択に成功。
  rproc-1開始失敗、unknown boot device: 13、load failed: uboot=-1 esos=-1でログが終わる。
  OpenSBIの起動表示はない。JTAG enabled on MMC1 pinsも記録されている。
- ソース証拠：固定コミットのdrivers/remoteproc/k3-rproc.cは約6秒の同期応答待ちが
  失敗しても0を返す。board/spacemit/k3/spl.cも開始失敗を表示するだけで続行する。
  arch/riscv/include/asm/spl.hで13はBOOT_DEVICE_BOARDだが、spl_extra_fit.cの
  switchにはこのcaseがない。common/spl/spl_opensbi.cは追加FIT処理の戻り値を無視し、
  U-Boot metadata探索失敗後にも未確定node/entryを使用し得る。
- 帰属：上記固定参照ソースと今回の入力組合せで確認。販売元4月版や上流一般に帰属しない。
  core 1が応答しない原因、OpenSBI無表示の直接原因、以前のUFS障害との因果は未確定。
- 修正候補：RAM統合FITでは永続媒体の追加FIT読込みを省略し、後段でloaded U-Boot metadataを
  必須検査する。RCPU同期timeoutを-ETIMEDOUTとし、SPLフックで失敗時に停止する。
  ESOS展開・ELFロード／開始とOpenSBI引渡しの診断ログを追加する。
  ESOSのタイムアウトを無視してOpenSBIへ進めたり、保護やリセット手順を省略したりしない。
- 検証範囲：固定ソースへのgit apply --checkと、実際のprepare-only CLIによる適用・
  source.patch生成・パッチSHA記録・既存output拒否を確認。Python構文、実FITツールの
  ホスト回帰23件に合格。実機の再試験とは分けて記録する。
  対応するK3 GCCでの修正候補の完全ビルド、実機再試験、QEMU guest統合は未検証。
  詳細：[参照FSBLの停止調査](jupiter2-reference-ram-boot-tests.md#8-参照fsblでの停止と診断版の再試験ksb-065)。
- 診断版のユーザー実機結果：rcpu0-fw展開260096 bytes、core 0 handshake acknowledged。
  rcpu1-fw展開284080 bytes、core 1同期値0のままtimeoutし、-110でOpenSBI前に停止。
  ユーザー環境でビルド・実機実行され、失敗時停止が機能することを確認した。
  同じmalloc領域104008640の再利用は前のバッファ解放後であり、それだけで重複障害と扱わない。
- 次の照合：固定SPL DTのcore 1 fw_boot_entryは0x100800000。
  以前のユーザーESOS FIT一覧のrcpu1-fw entry/loadは0x100804000。
  FITの値をELFのentryと同一視せず、実ELFのentryとPT_LOAD配置を確認する。

### KSB-066: RCPU診断entryの書式がSPL tiny printfに非対応

- 登録日：2026-11-21。ユーザー実機の診断ログでcore 0/1ともentry=0xxと表示。
- 原因・帰属：本リポジトリで追加した%llxに対し、固定ソースlib/tiny-printf.cは
  長さ修飾子lを一つだけ処理する。設定はCONFIG_SPL_USE_TINY_PRINTF=y。
  この表示は起動アドレスがゼロである証拠ではない。こちらが追加した診断コードの欠陥。
- 修正：RV64 K3ではulongが64 bitなので、%lxと(ulong)キャストへ変更する。
  実際の起動アドレス設定、RCPUのリセット、応答待ち処理は変更しない。
- 検証：固定ソースの書式処理と設定を確認。git apply --checkで適用確認する。
  その後のユーザー実機でcore 0=0x100200000、core 1=0x100804000の表示を確認。

### KSB-067: 参照SPL DTと販売元RCPU core 1のELF entry不一致

- 登録日：2026-11-21。ユーザー提供rcpu1-fw.elf（284080 bytes）をreadelfで検査。
  SHA-256: edbd613a0008a97ac94f589afd7d60c770dd809ae2e4260c54fe247fa42ab4ca。
  ELF64 little-endian RISC-V EXEC、entry=0x100804000。
  実行可能LOADは物理・仮想とも0x100804000、file/mem size=0x44000。
  別のRW LOADは0x100e00000、size=0x100（resource_table）。
- 不一致：参照コミット4c294a06のarch/riscv/dts/k3_spl.dtsは
  rcpu@1/fw_boot_entry=<0x1 0x800000>、つまり0x100800000。
  k3-rproc.cはDT値を起動レジスターへ書く。ELFロード関数はPT_LOADのp_paddrへ配置する。
  このELFには0x100800000から0x100803fffをロードするセグメントがなく、
  設定された起動先が実行可能コードより16 KiB手前である。
- 帰属：固定参照ソースと今回の販売元ESOSの組合せの互換性不良。
  ESOS core 1応答失敗の原因となる具体的な設定不一致は確定したが、
  修正後の起動成功、唯一の原因であること、以前のUFS障害との因果は未確認。
- 修正候補：ESOS FITの選択済みrcpu0-fw/rcpu1-fwを展開し、実ELFのentry/LOADを検査する。
  両coreのSPL DT起動先をそれぞれの実ELF entryから設定し、差分とELFハッシュ・配置を記録する。
  コンパイル後のSPL DTBにも同値があることと、そのDTBがFSBL内にあることを必須検査する。
  FIT entryからの推測や、timeoutの無視で回避しない。
- 検証：ユーザー実ELFとreadelfの一致、固定ソースDTSの変更、dtcによるDT照合を確認。
  実LZO FITからのprepare-only CLIでcore 1のユーザー実ELFを展開・反映・ハッシュ記録。
  core 0はこのホスト試験に限りLLVM生成の形式試験用ELFを使用した。
  新しいELF/DTホスト試験3件、既存FITホスト試験23件が合格。
  その後のユーザー実機でcore 1 entry=0x100804000、両core handshake acknowledgedを確認。
  ユーザー環境でビルド・実機実行された。ESOS/RPMI全機能やUFSの成功を意味しない。
  開発環境でのK3 GCC完全ビルドとQEMU guest統合は未実施。後段はKSB-068で追跡する。

### KSB-068: RCPU応答後のOpenSBI引渡し前表示で無出力

- 登録日：2026-11-21。KSB-067修正後のユーザー実機ログで、core 0/1とも
  handshake acknowledged。RAM統合FITの追加読込み省略も通過。
  最後の表示はOpenSBI entry=0x100000000 next=0x102000000 dtb=102153cf0 hart=0。
  OpenSBIバナー、U-Bootプロンプトは出ていない。
- 到達判定：最後の診断表示はspl_invoke_opensbi()の呼出し直前にあり、
  OpenSBI内部へ入った証拠ではない。RCPUの応答もRPMI全サービスの健全性の証明ではない。
- 原因：未確定。引渡しABI、実際のOpenSBI BINのリンク先・初期コード、同梱DTと
  販売元OpenSBIの組合せ、初期化待ち・UART経路を照合する。
  SPLのFITコピー経路には既にD-cache flushがあり、無出力だけを根拠にcacheやPMPを変更しない。
- 次の資料：今回転送したrelease/images/ram-boot-vendor.itbを解析する。
  同梱OpenSBI/DTB/ESOSのハッシュと配置、OpenSBI初期命令とヘッダー、console/RPMI設定を確認する。
  FIT内のDTはSPLによる実行時fixup前であり、必要なら次に実行時FDT/引渡し情報を採取する。
- 状態：未修正・調査中。UFS試験へは進まない。詳細は参照RAM起動テスト手順の第11節。
  提供FITの解析でKSB-069の具体的なqueue設定不一致を確認し、次の修正候補とした。

### KSB-069: OpenSBI用DTと有効なESOS RPMIサーバーの共有領域不一致

- 登録日：2026-11-21。ユーザー提供ram-boot-vendor.itbは2191805 bytes、
  SHA-256 cf820239195bc9f3dc825b7247e891ae0b59663c5d45e644bea294f999e58d95。
  OpenSBIは270552 bytes、SHA-256 33072ac8216a74981ed36785a7d515f3c3cadcab3cef8d775972c28e2b9e6a9c。
- 証拠：FITのOpenSBI/U-Boot用DTはRPMI queueを0x100e00000から4本指定する。
  同じFITのrcpu0-dtb-pico-itxはrpmi@2がokay、shmem-base=0x100800000。
  rcpu1-dtb-pico-itxの0x100e00000側rpmi@2はdisabled。
  有効サーバーはcore 0、共有領域0x4000、各queue 0x1000、slot 0x100。
  mailbox3のbase=0xcac90c00、channel=0でAP側doorbell baseとは一致する。
- 影響：OpenSBIと有効ESOSサーバーが異なるqueue領域を参照する。
  0x100e00000はcore 1 ELFのresource_table LOADとも重なる。
  具体的な設定不一致は確定。OpenSBI無出力の唯一の原因と断定せず、実行時fixupも照合対象。
- 帰属：固定参照ソースと今回の販売元ESOSの組合せの互換性不良。
  参照k3.dtsiは0x100e00000で、今回のESOSと版・構成が揃っていなかった。
- 修正候補：選択済みPico用ESOS DTを展開して、有効なRPMIサーバーが一つであることを確認する。
  queue/slotサイズとmailbox provider/channelを検査し、その契約をPico用U-Boot DTへ反映する。
  共通k3.dtsiや他ボードは変更しない。最終U-Boot FITの選択DTも同じ契約であることを必須検査する。
  ESOS/DTハッシュと契約をrecords/rpmi-contract.jsonへ記録する。
- 検証：実入力の不一致拒否、固定ソースのPico DTSのcpp/dtc生成後の一致を確認。
  実FITから同梱OpenSBIと全27 ESOS payloadを取り出した入力でprepare-only CLIが通り、
  両entryと有効サーバーの契約・ハッシュ・ソース差分を記録した。
  ELF/RPMI DTホスト試験6件、FITホスト試験23件が合格。修正後のK3 GCC完全ビルド、
  OpenSBI/RPMI/UFSの実機成功、QEMU guest統合は未確認。

KSB-068/069の実機追記（2026-11-21）：ユーザーからU-Boot 2022.10-g4c294a06-dirty
（Nov 21 2026 13:06:35 +0900）の起動とUARTの=>を報告。
Model=spacemit k3 pico itx board、Loading Environment from nowhere... OK、In/Out/Err=serial。
今回の修正後RAM起動経路でOpenSBIからU-Bootへ引渡しが進んだ到達証拠として記録する。
この抜粋にはOpenSBIバナー自体はなく、全SBI/RPMI機能やUFS・Linuxの成功とは扱わない。
次はUARTでscsi scanとscsi infoを一度実行してKSB-063のUFS列挙を確認する。

KSB-063/069の実機追記（2026-11-21）：修正後の参照RAM起動でscsi scanとscsi infoが成功。
Device 0 (0:0)、Vendor YMTC、Product YMUS8B5TH1A1C1、Rev 0303、
容量122056.0 MB / 119.1 GB（31246336 x 4096 bytes）。gear 3、lane 2、FAST MODE、rate 2。
今回のログには以前のUIC_ERROR、descriptor失敗、UTP timeoutはない。
新しい参照FSBL/U-BootとESOS起動先・RPMI DT整合を含む構成でのUFS列挙合格とする。
どの変更単独で以前の全試行の障害が解消するかは分離検証していない。
パーティション・ファイル読出し、Linux起動、開発版OpenSBI/SM、Enclave実行はまだ未確認。


KSB-063/065/067/068/069の到達結果追記（2026-11-21）：ユーザーからLinux起動成功の報告を受領。
販売元OpenSBI、修正した参照FSBL/U-Boot、同梱ESOSをRAM起動し、UFSのkernel/initrd/DTBでLinux起動。
各修正単独の効果を分離した検証ではない。unameの実出力、開発版SM/Enclave動作、
QEMU guest統合はこの報告に含まない。再現操作は[RAM起動ガイド](jupiter2-ram-boot-guide.md)へ集約。
新操作スクリプト自身のUSB実行は実機未確認で、ホストのdry-run等の検査と区別する。

### KSB-070: Linux用DTの直接mailbox controllerとSMのM-onlyページが不整合

- 登録日：2026-11-21。ユーザー提供k3-pico-itx.dtbは148441 bytes、
  SHA-256 de39ef1acaf7fc13b365a55b1c007f8888c36a06b9840598762ce03a9aa5f129。
- 証拠：/soc/mailbox0@cac90000からmailbox3@cac90c00までの4 controllerがokay。
  SMのKSB-058対応は0xcac90000–0xcac90fffをM-mode専用にする。
  対象4 controllerを指す有効なmboxes利用者はなく、mailbox 3の参照者rcpu_rproc0はdisabled。
  mailbox 4を使うrcpu_rproc1と、SBI MPXYを使うRPMIクライアントは有効で、変更対象にしない。
- ソース確認：linux-k3/drivers/mailbox/spacemit/k3-mailbox.cのprobeはIRQを登録し、
  IRQハンドラーはreadl/writelでcontrollerへ直接アクセスする。
  有効remoteproc利用者がいないだけでは、LinuxがM-onlyページへアクセスしない保証にはならない。
- 帰属：今回のBianbu Linux DTとK3 SMのページ所有契約の互換性不良。
  提供DTBで不整合は確認したが、このDTBとSM版Linuxの実機trapを既に観測したとは主張しない。
- 修正候補：元DTBを残し、対象4 controllerのstatusだけをdisabledにした別名DTBを生成。
  scripts/prepare-jupiter2-keystone-linux-dtb.pyは有効利用者がいれば拒否し、
  他ノード・未知のプロパティを保持していることを検査する。
  有効なremoteproc 1やmailbox 4以降、SBI MPXY、reserved-memoryを自動停止・変更しない。
- 実入力の候補：148457 bytes、SHA-256
  54a6e7855c04dc17c67d13526a6e917f5f971a95d7b1d82894509d6aada4db5d。
  入出力DTB全体は公開せず、変更対象・hash・利用者の状態だけを記録する。
- 検証範囲：実DTBを実fdtputで変更して全ノード・プロパティを照合。
  新しいDTホスト試験6件で有効利用者の拒否、元ファイル保持、他ノード保持、再実行を確認。
  実機追記：別名DTB（148457 bytes）のloadとLinux起動を利用者が確認。SM版Linuxは8 CPUのみ起動し、helloはKSB-071に関連する受付条件で停止。hello二種の成功と同じ実機DTを使うQEMU統合は未検証。
  [SM起動からアプリ試験までの手順](jupiter2-keystone-app-test.md)に段階と判定を記載。

### KSB-071: X100/A100のPMP数混在を16個固定の移植処理が拒否

- 起源：本リポジトリのK3 Keystone向け追加処理。上流Keystone/OpenSBI一般の欠陥とはしない。
- 条件・証拠：2026年11月21日提供のUART log.txtの末尾側起動で、Hart0〜7はPMP16個でSM初期化成功、Hart8〜15は32個を検出直後にPMP configure rc=-2、Linuxは8 CPUのみ起動。
- 直接原因：opensbi/lib/sbi/sbi_hart.c の k3_root_pmp_layout_build() が count != K3_BOOT_PMP_COUNT（16）を拒否する。関連するboot slot計算、snapshot、preflight、partition evidenceにも16個固定の表現がある。
- 影響：A100がLinuxへ到達せず、sm_is_ready()の全16 Hart STARTED条件を満たせない。CPU3へのtasksetでもhello CREATEが100100で拒否される。SM not initializedという共通診断は実際の拒否条件を区別できない。
- 方針：[混在PMP対応計画](jupiter2-heterogeneous-pmp-plan.md)。共通16個の配置を維持し、32個側の追加範囲は全数検証して無効状態を要求する。追加範囲の実態を未確認のまま無視・解除しない。
- 状態：共通16個と実装16/32個の分離、全追加範囲の検査、32個snapshot/証拠管理、SM拒否理由の診断を実装。SMのmixed/qemu16各30単位コンパイルとmixedのOpenSBIリンクを確認。QEMU専用S-mode guestで一律16個と16/32混在の全16 Hart readback・HSM到達を確認。Linux/SDKのguest統合、修正版実機起動、hello成功は未検証。提供ログには複数回の過去試行が含まれ、末尾側の起動を根拠としている。修正commit：[9bfb8bf74f62](https://github.com/yutaka-ishikawa/public/commit/9bfb8bf74f62f1c253be9fd11f6bc36a03b02105)。
- 後続確認：実機の新dmesgでは全16 CPU起動を確認（firmware hashは未照合）。KSB-073修正後の実QEMU/Linuxでは、混在構成を含むhello二種8回が正常終了。全run-allや修正版実機helloの結果とは区別する。

### KSB-072: QEMU試験条件と実機のPMP・起動契約が不一致

- 区分：Jupiter2部分モデルの検証範囲不足。上流QEMUが32 PMPを扱えないという欠陥ではない。
- 証拠：run-k3.shは全Hartにrva23s64、num-pmp-regions=16、pmp-granularity=16バイトを指定。実機UARTではX100=16、A100=32、全体の粒度4 KiB。実機root規則数・ロックとESOS/RPMI等も従来モデルでは再現していない。
- 影響：KSB-058〜060/071等の実機固有条件を従来のQEMU PASSから判断できない。既存の部分モデルという説明だけで回帰試験の不足を補えない。
- 候補：QEMUのCPU realize前に実PMP CSR backendのHart別個数と粒度を設定するmixed-pmpオプションを追加。一律16個の既定構成も維持。CPU ISAは同一rva23s64のままで、X100/A100全体の再現とはしない。
- 残課題：[QEMU差分一覧](jupiter2-qemu-hardware-test-gaps.md)に優先順位、実機domain fixture、上位PMPの負の試験、mailbox/RPMI/ESOS/UFSの未再現範囲を記載。
- 検証：QEMUビルド成功。実QMPで両構成の全CPU設定を確認し、実OpenSBI/SM＋専用S-mode guestで全16 HartのreadbackとHSM到達を確認。ただし実測root7個・空き9個・PMPADDR幅54ビットであり実機の13個・3個・38ビットとは異なる。Linux/SDKのguest統合と実機試験は未実施。修正commit：[9bfb8bf74f62](https://github.com/yutaka-ishikawa/public/commit/9bfb8bf74f62f1c253be9fd11f6bc36a03b02105)。

### KSB-073: 全16 CPU起動後、hello二種のhost runnerがload access faultで停止

- 入力：2026年11月21日提供のdmesg.txtと実機配置済みhello.ke/hello-native.ke。Linux 6.18.3で全16 CPU起動を確認。旧firmwareのhashは未照合。hello-nativeの終了コード139。
- 観測：hello-runnerはCPU2でepc=0x2aaefb129c、ELF内位置0x529c、badaddr=0x3fa252a000。hello-native-runnerはCPU1でepc=0x2ae5c49244、位置0x5244、badaddr=0x3fb2373000。両方cause=5（load access fault）、SIGSEGV code=2。直前にEPM 4 MiBを物理0x11c000000へ割り当てている。
- 同一ELFによる特定：両方のEPCはdispatch(void*)+8のld a4,0(a0)、RAはEnclave::run内のOCALL callback呼出し直後（0x6092/0x603c）に一致。UTM上edge_call headerの最初の読取りで停止している。CREATE/RUNを経たOCALL復帰後であり、初期ELFロード中の失敗とは区別する。
- ソース上の原因：KSB-062でK3のUTMを独立slot化したが、revoke_region()がREGION_UTMにもNO_PERMを残す。後段のOS許可より優先され、ホストの共有bufferアクセスを遮る。上流一般ではなくK3移植の組合せの不備。実機CSR/PTEのdumpは未採取で、修正版による実機確認を要する。
- 修正候補：K3のUTMだけをホスト復帰・失敗rollback時にk3_pmp_apply_verifiedでUNSETしCSR readbackを行う。EPMのNO_PERMは維持する。汎用UTMとBACKINGは変更しない。対象：keystone/sm/src/enclave.c。
- 検証：SM全30単位クロスコンパイル、OpenSBIリンクとmtvec整列に成功。実QEMU＋Linux 6.18.3＋実driver＋提供SDK/Eyrie/sampleで比較し、修正前は一律/混在の両構成でhelloのrunner+0x529c、cause=5、終了139を再現。修正後は両構成×CPU3/8×hello/nativeの計8回が正常出力・終了0・DESTROY。全12 sample、run-all全体、EPM拒否の負の試験、修正版の実機試験は未実施。
- 過去のPASSとの関係：保存済みsample成功記録は11月9日。UTM独立slot化は11月21日で、その後の同一成果物のsample回帰確認が不足していた。今回QEMUでも障害を再現し、修正前後の比較を記録した。
- 詳細・package/runner hash・再試験手順：[UTMホスト復帰の解析](jupiter2-utm-host-access-issue.md)。修正commit：[76fd41362565](https://github.com/yutaka-ishikawa/public/commit/76fd41362565e0f53f7216a42fa95ac41df1271e)。

### KSB-074: OPTEEDの呼出元・メッセージ長・切替結果の検査不足

- 対象は [K3のOPTEED dispatcher](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c)。
  ベンダー取込コードでCOMMUNICATE/COMPLETEの呼出元domainとABI長の検査がなく、
  context切替の戻り値も破棄していた。K3 Keystone構成では未対応の切替経路に
  到達すると、ガードがhartを停止する。
- `4b0f75220` で呼出元domain、ABI長、共有領域と応答長を検査し、
  切替エラーをMPXYに返す。Keystone構成では共通PMP切替を実装するまで
  dispatcherが処理を拒否し、共有領域やdomain contextを更新しない。
- 通常K3構成とK3 Keystone構成のOpenSBIをビルドした。16 hartのK3 QEMUで
  Keystone構成のファームウェアの起動ログを確認した。OP-TEEとLinuxを含む
  実ゲストのMPXY経路、domain切替、実機は未検証。

### KSB-075: ドメイン切替でSstcタイマー期限を引き継ぐ

- 対象は取込済みのOpenSBI `sbi_domain_context.c`。Sstcを備えたhartでの切替時に
  `stimecmp` が保存・復元の対象外だった。ソース上、切替元の期限が切替先にも
  適用され、切替先が期限を上書きすると切替元へ復帰した後もその値が残る。
- `5008b3157` ではK3 Keystone構成の切替経路に `stimecmp` の保存・復元を追加した。
- 通常のOP-TEE構成にも適用した試行では、K3 QEMUのLinuxがOP-TEEの非同期通知設定を
  読んだ後にドライバ初期化を完了せず、試験がタイムアウトした。通常構成から適用を
  外した。停止の原因は未特定。
- 同居構成で保存・復元が必要という実行結果が得られていないため、K3 Keystone構成からも
  変更を外し、従来のタイマー処理に戻した。

### KSB-076: OP-TEE先行起動でK3 Keystoneの初期PMP設定が停止

- 16 hartのK3 QEMUで同居試験用DTBのCPU `opensbi-domain` だけを、動作済みの
  単独構成と同じ `optee-domain` に全hart分揃えた。既存のOpenSBI処理はhart 0を
  OP-TEEの起動hartに設定した。
- `sbi_hart_keystone_check_optee_pmp()` は現在のドメインがLinuxと一致しないため
  `-3` を返した。続く初期PMP設定も現在のOP-TEEドメインからLinux向けの配置を
  組み立てようとし、`regular=6 broad=0` で `-2` を返した。OP-TEE Coreに入る前に停止した。
- 対処候補は、Linuxドメインから固定枠の配置を決め、起動時の所属に合わせて権限を設定・検証すること。
  既存のOP-TEE起動経路とタイマー処理を使い、Linuxへの引き渡しでLinux用権限に復帰する。
- Linuxの配置でK3のPMP初期検査とSM初期化を終え、S-modeへ入る前にOP-TEE用の
  権限を設定するよう変更した。K3 QEMUでSM初期化まで到達した。切替検査は
  KSB-077修正後も、`sm_init()` がOS用に設定した枠14の全域RWX（`prot=0x1f`）を
  検出して `-4` を返す。この枠が有効な間はOP-TEE Coreへ入らない。
- Keystone側でOS用枠を特定し、各hartのOP-TEE移行時に無効化する。Linux用の固定枠を
  復元した後にOS用枠を復元し、いずれもCSRを読み戻す。移行失敗時も元のLinux用枠を
  復元し、その確認に失敗すればhartを停止する。
- K3 QEMUでOP-TEE Coreへ到達した後、DTB読取り中の `fdt32_ld` で
  load access fault（cause 5、tval `0x173400004`）が発生した。Linuxへの復帰と
  復旧の異常系は未試験。Keystone単独構成では16 hartで `hello` と `hello-native` が成功した。
- `0x173400004` は外部DTBへの仮想アドレス。OP-TEEに渡された物理DTBは
  `0x181e00000` で、初期の同居用DTBはこの範囲をOP-TEEの固定枠に含めていなかった。
  外部DTBとGEU・PMUMAIN・PMU APの固定範囲を追加し、K3 QEMUで外部DTBの読取りと
  主hart・副hart 15個の初期化を確認した。MPXYの既存ガードが残るためLinuxへの引き渡しは未確認。
- 主hartの起動完了通知を許可し、既存のドメイン終了経路でLinuxに引き渡した。
  K3 QEMUでOP-TEEのエントリ登録とLinuxの起動ログを確認した。

### KSB-077: KeystoneのPMP初期化で設定ビットが別の枠に残る

- K3 QEMUのOP-TEE先行起動で、SM初期化後にKeystone枠13からNAPOT・RW
  （`prot=0x1b`）を読み戻した。`PMP_SET` は引数へ既存の同期グループの設定を
  ORするため、`pmp_init()` のループで値を再利用すると前の枠・グループのビットが残る。
- K3では各Keystone枠を既存の `PMP_UNSET` で個別に消去する。QEMUの再試験では
  枠13による停止が解消し、次の検査で意図的に設定されたOS用の枠14を検出した。

### KSB-078: OP-TEE先行起動後にLinuxが副hartを開始できない

- K3 QEMUで副hartのOP-TEE起動完了通知も許可した試行では、Linuxが副hartの
  起動失敗を記録した。既存のドメイン終了経路は副hartを `sbi_hsm_hart_stop()` で
  停止するが、K3 Keystoneの固定オンライン方針が内部呼出しも `SBI_EDENIED` で拒否する。
- 副hartの初回引き渡しには専用の内部HSM停止を使う。動的PMP更新前に限り、
  KeystoneのHSM/PMPゲート内で停止台帳を更新して `STOPPED` を公開する。
  Linuxからの再始動では保持したOpenSBIのPMP設定を読み戻し、Keystoneの許可枠を再設定する。
- K3 QEMUの単一スレッドとマルチスレッドTCGで、Linuxによる全16 CPUの起動を確認した。
  LinuxからのTA要求は既存のMPXYガードで拒否され、同居ゲストの電源断も完了していない。

### KSB-079: OP-TEEとのPMP更新競合でKeystoneのDESTROYを再試行できなくなる

- OP-TEE実行中に個々のKeystone全hart PMP更新を拒否する試作では、
  `destroy_enclave()` が先に状態を `DESTROYING` に変える。後続の `pmp_unset_global()` が
  競合を返すと、現行の異常処理は領域を隔離したままにし、通常のDESTROY再試行を受付けない。
- 競合は状態変更前に判定する必要がある。明示DESTROYとファイルを閉じたときの後処理では
  再試行の責任が異なる。検証はソースの確認までで、競合のQEMU再現は未実施。
- CREATEとDESTROYのSBI入口でEnclave操作を予約する。競合時のDESTROYはLinuxへ
  `-EAGAIN` を返す。closeで競合した場合、ドライバーはEnclaveの管理情報を保持し、
  遅延ワークで再試行する。PMP更新そのものが失敗した場合は既存の隔離を維持する。
- OpenSBI、SM、Linuxモジュールをクロスビルドした。K3 QEMUではKeystone単独の
  初回試行でPMP同期が失敗し、トレース有効の再試験と通常ビルドの再試験で `hello` と
  `hello-native` が成功した。同居構成ではOP-TEEドライバーの初期化と16 CPUの
  `TEEC_InitializeContext` 成功を確認した。この時点の並行TA試験はタイムアウトした
  （KSB-080）。closeの競合処理は未確認。
- `31673e834` のK3 QEMU同居ゲストで競合を確認した。明示経路ではCPU 2の最初の
  DESTROYが `-EAGAIN`、CPU 3のTAが期待値42を返した後の再試行が成功した。
  close経路ではテスト用ドライバのログで遅延ワークの破棄成功を確認した。
  この試行ではTA応答が不正となり、試験全体は失敗した（KSB-081）。

### KSB-080: OP-TEEの16 CPU並行TA試験がPMP詳細ログでタイムアウト

- K3 QEMU（16 hart、マルチスレッドTCG、起動hart 0固定）で、同じDTB、Linux、
  initramfs、OP-TEE ELF、100秒の制限を使って比較した。旧ビルドではLinuxの
  OP-TEEドライバー初期化と `TEEC_InitializeContext` の後もPMP領域の詳細ログが
  出続け、TA応答の確認前にタイムアウトした。
- 実行時のLinux・OP-TEE切替では、通常のPMP領域一覧の出力を抑制した。起動時の
  一覧、配置の検査、拒否時の診断、CSRの読み戻しは維持した。
- 修正後は同じK3 QEMU試験で `PASS: parallel OP-TEE TA calls on all 16 CPUs` を
  確認した。このinitramfsの試験対象はTA呼び出しで、Enclaveとの同時実行は未検証。

### KSB-081: Keystoneの遅延DESTROY中にOP-TEEのRPC復帰が失敗する

- 16 hartの同居ゲストで、CPU 3の長時間TA呼び出し中にCPU 2でDESTROYを発行し、
  `-EAGAIN` の後にプロセスがファイルを閉じた。診断付きOpenSBIの再試験で、
  RPC復帰 `0x32000003` のPMP予約が `SBI_EINVALID_STATE`（`-10`）で拒否された。
- LinuxはMPXYエラー `-524` を記録し、TAの呼び出し結果は `rc=0` だったが、
  入力41が未変更で検証マーカーは0だった。遅延ワークは破棄を完了した。
- MPXYの予約競合を再試行可能な状態として通知し、Linux側で同じ要求を再送する案と、
  RPCからの復帰までKeystone側のPMP更新を延期する案がある。
- PMP予約の競合だけを `SBI_EINVALID_STATE` としてMPXY経由でLinuxへ伝え、
  OP-TEEドライバーが最大1秒、同じ要求を再送する。通信エラー時は応答を処理せずエラーを返す。
- 16 hartのK3 QEMU同居ゲストで明示DESTROYとcloseを順に試験した。両方で最初の
  DESTROYは `-EAGAIN`、明示再試行と遅延ワークは破棄に成功し、TA応答はともに
  42かつマーカー `0x4a325441` だった。試験用ドライバーの追加ログで遅延ワークの結果を確認した。
- `7eef141ee` の反復試験では、明示DESTROYは3回とも競合後の再試行に成功した。
  close経路は3回中2回で競合が起き、両方で遅延ワークの成功とTAの正しい応答を確認した。
  残る1回は最初のDESTROYが成功し、close後の遅延ワークを通らなかった。

### KSB-082: 同居ゲストのEnclave実行中に外部割り込みで停止

- `7eef141ee` の16 hart K3 QEMU同居ゲストで、CPU 2のEnclaveが共有メモリを
  確認し、CPU 3のTA呼び出しがそのメモリへ結果を渡す試験を反復した。
  1回目はTA応答・Enclave終了・破棄に成功。2回目はhart 2で
  `unhandled external interrupt (error -2)` と割り込み番号 `0xb` を記録して停止した。
- `sbi_trap_handler_keystone_enclave()` はM-modeのタイマーとソフトウェア割り込みを
  受けてEnclaveを中断する。M-mode外部割り込みは既定のエラー経路に入る。
  どのデバイスが割り込みを送ったかと、同居構成固有の条件かは未特定。
- CPU 8のEnclaveとCPU 15のTAで試した回は双方が完了し、Enclaveの破棄に成功した。
- 診断ビルドの実QEMUで再現した3回ともhart 2で `irq=11 mtopei=0x10001 mip=0x800`
  を確認した。`mtopei` の割り込みIDは1で、OpenSBIのIMSICドライバーがIPIに
  割り当てるIDと一致する。
- 送受信の診断を加えた実QEMU試験の5回目では、受信hart 2の保留ビットは `0x10`
  （イベント4、`IPI_TLB`）だった。送信元はLinuxドメインのhart 3で、保存された
  SBI呼出しはRFENCE拡張 `0x52464e43` の `REMOTE_SFENCE_VMA_ASID`（機能2）だった。
  `0xffffffff80010e8a` を試験ビルドのLinux `vmlinux` で照合すると `__sbi_ecall` に一致する。
  この再現のIPIはLinuxによる別hartのTLB無効化要求。Linux内で要求を起こした上位処理は未追跡。
- 通常のOpenSBIトラップはM-mode外部割り込みをIRQチップに渡し、IMSICはID 1を
  `sbi_ipi_process()` へ渡す。KeystoneのEnclave用トラップもこの配送を扱い、必要な
  Enclave中断とLinux復帰を既存の保護条件で扱う必要がある。
- K3のEnclaveトラップでM-mode外部割り込みを受けた際は、EnclaveのPCを保存して
  ホストへ戻す。割り込みは保留したままにし、復元したOpenSBIトラップベクタで処理する。
  K3ではM-mode外部割り込みをソフトウェアでS-mode外部割り込みへ変換しない。
- 修正版の16 hart K3 QEMUで、同時実行を4回確認した。うち1回はEnclave上の
  hart 2で外部割り込みを観測した。別の試験ではCPU 3から同じプロセスの通常ページに
  `mprotect()` を発行し、hart 2の外部割り込み、`mprotect()` の復帰、TA応答、
  Enclaveの正常終了と破棄、電源断を確認した。同じ `mprotect()` 試験を修正前の
  診断ビルドで実行すると、hart 2がLinuxからの `IPI_TLB` で停止した。
  通常ビルドのKeystone単独構成でも
  `hello` と `hello-native` が成功した。実機は未試験。

### KSB-083: 同居ゲストがOP-TEEの副hart初期化で停止

- `7eef141ee` の16 hart K3 QEMU同居ゲストをマルチスレッドTCGで起動した。
  同時実行試験の3回目はOP-TEEの主hart初期化後、hart 9の初期PMP設定成功を
  記録したが、hart 9のOP-TEE初期化完了とLinuxへの引き渡しは記録されなかった。
- 起動hartはDTBで0に固定していた。100秒でタイムアウト（終了コード124）し、
  TA・Enclave同時実行の試験には到達していない。停止箇所の特定と再現条件の調査が残る。
- 候補は `k3_keystone_hsm_start_finish()` の共有HSM/PMPゲート取得。別hartと競合すると
  即時エラーを返し、呼び出し側が診断を出さずにhartを停止する経路がある。
  診断ビルドを9回実行し、いずれもLinuxの16 CPU起動まで進んだ。起動停止は再現せず、
  このコード経路が該当のhart 9で発生したことは未確認。
- 追加の診断ビルドで通常条件8回とQMP監視付き12回は全16 CPUでLinuxまで進んだ。
  ホストCPUを2個に制限した別の10回では9回でLinuxが起動し、1回は20秒で
  タイムアウトした。この1回にHSMゲート競合の診断は出ていない。
- K3 QEMUの診断ビルドで、hart 8が共有ゲートを保持している間にhart 9の初回HSM起動完了を
  実行させた。hart 9の初期PMP設定は成功したが、HSM起動完了が
  `SBI_EINVALID_STATE`（`-10`）を返した。残る副hartはOP-TEE初期化を完了し、
  hart 9の初期化とLinuxへの引き渡しを待ったままタイムアウトした。
  この競合で元の症状が起こり得ることは確認したが、自然発生した回の原因は未確定。
- 診断コードなしの起動試験をホスト1 CPUに制限し、Linux未到達の時点でQMPから
  レジスタを2回採取した。多くの副hartのPCは `spin_lock()`、戻り先は `sbi_printf()`、
  対象は `console_out_lock`（ファームウェア相対 `0x42028`）。hart 9のレジスタでも
  約3秒間にロックのowner番号が `0x359` から `0x3c2` に進んだ。
- ホスト1 CPUで同じ16 hartの試験を交互に実行した。Linux起動ログまでの時間は
  `K3_PMP_BOOT_TRACE=1` で20.48秒と19.87秒、`=0` で2回とも0.72秒だった。
  今回の短い観測でLinuxへ未到達だった事象はコンソール出力の遅延で説明できる。
  元の100秒タイムアウトをこの遅延で説明できるかは未確定。
- 詳細ログなしの構成でホストCPU数を1〜3に変えながら16回起動し、全回でLinuxの
  16 CPUがオンラインになった。別の実QEMU試験でTAとEnclaveの同時実行、
  全16 CPUの並行TA呼出しも成功した。明示DESTROYは `-EAGAIN` 後の再試行に成功し、
  close単独の競合試験でも遅延ワークとTA応答が成功した。製品ソースは変更していない。
- `7eef141ee` と同じファームウェアソースで診断コードを追加せず再ビルドした。
  元の16 hart、2 GiB、マルチスレッドTCG、起動hart 0、PMP詳細ログありで反復し、
  最初の3回はLinuxに到達、4回目は起動停止が自然発生した。hart 11はPMP設定成功後に
  OP-TEE初期化完了を出さず、残る副hartは完了した。100秒超でLinux未到達、観測後半に
  UART出力は増えなかった。
- 4回目のQMPレジスタを約3秒間隔で2回採取した。hart 11は `sbi_hart_hang()` に留まり、
  `ra` は `sbi_hsm_hart_start_finish()` のエラー分岐の直後、`a0=-10`、`a1=11`、
  `a3=1` だった。当該ELFの逆アセンブルでは、このレジスタの組合せは共有HSM/PMPゲートが
  使用中のときに返る分岐と一致する。起動台帳の更新に失敗する後段の経路は `a1=1` を返す。
  主hartはOP-TEEの副hart完了待ち、他の副hartはOpenSBIのHSM待機にいた。
  この自然再現で原因経路を確認した。初回のhart 9にはレジスタ採取がない。
- HSM起動完了で共有ゲートの取得に失敗した場合は、台帳の更新と `STARTED` 公開の前に
  最大100 ms再試行する。取得後は既存の起動完了処理を使い、起動完了に失敗した場合は
  hart番号とエラーを記録する。
- 16 hart K3 QEMUの通常ビルドで4回起動し、毎回Linuxの16 CPU起動、TAとEnclaveの
  同時実行、電源断を確認した。別の診断ビルドではhart 9のゲート再試行を実際に発生させ、
  同じ確認項目がすべて通った。修正後に100 msを超えるゲート競合は観測していない。
  修正前の100秒はQEMU試験全体のタイムアウトであり、ゲートの保持時間は測定していない。
  100 msを超える競合の強制試験と実機試験は実施していない。

### KSB-084: QEMUのfTPMモジュール登録中に間欠的にタイムアウト

- 対象はKSB-083修正入りOpenSBI、Linuxの `tpm_ftpm_tee`、SpacemiT OP-TEE、
  REEからロードするfTPM TAを組み合わせたK3 QEMUの16 hart構成。
  `tee-supplicant` 起動後に `microsoft,ftpm` のDT経路でモジュールを登録する。
- 初回はLinuxの16 CPU起動とfTPM TAのロード後、`/dev/tpmrm0` の合格出力に
  到達せず、ホスト側の180秒制限でQEMUが終了した。別のQMP監視付き試行でも、
  fTPMのストレージ呼出し中にUART出力の進行が断続的に止まった。
- 診断コードなし・CPU固定なしの再試験は、モジュール登録後の
  `/dev/tpmrm0` 経由の `TPM2_GetRandom(16)` に成功し、QEMUは正常終了した。
  診断用initを使った試行でも、CPU割当てを変えない構成と、試験プロセスおよび
  supplicantをCPU 0に固定した構成で同じ応答と電源断を確認した。
- 停止箇所の関数、CPU割当てとの因果、実機での再現性は未確定。
  手順は [fTPM TAのビルドとQEMU試験](jupiter2-ftpm-ta-test.md) を参照。
- 診断用initで16 hart QEMUを5回起動し、3回はTPM応答と電源断に成功した。
  1回はTPM応答後の電源断で、もう1回はモジュール登録中に105秒のホスト側制限に
  達した。登録中のPID 1は `finit_module → ftpm_tee_probe → tpm_chip_register
  → tpm2_auto_startup → tpm2_get_cc_attrs_tbl → tpm2_get_tpm_pt` の
  TPMプロパティ取得から、OP-TEEの `handle_rpc_supp_cmd → optee_supp_thrd_req`
  に入り、RPC応答を待っていた。電源断時も `tpm2_shutdown` から同じRPC待機に入った。
- 待機前のUARTにはTAの `syscall_storage_obj_open` が出ていた。登録中の別試行では
  `optee_open_session` からも同じRPC待機を確認した。登録中・電源断時とも
  `tee-supplicant` は生存し、採取したスタックには `optee_supp_recv` で
  次の要求を待つスレッドがあった。これらのスタックだけでは、対象要求が
  受信前、処理中、応答後の呼出元起床待ちのどこにあったかは確定できない。
- 過去の180秒・300秒タイムアウトのTAシステムコール列は、それぞれ成功時の先頭
  3,147件・1,685件と一致した。途切れた地点が異なるため、最終UART行だけで
  失敗したTA関数を断定できない。今回確認できた停止箇所はLinux側のRPC完了待ち。
- Keystone入りOpenSBIの診断ビルドで、LinuxからOP-TEE実行中のhart 1に向けた
  SBIソフトウェアIPIを観測した。電源断時の送信元はhart 15だった。
  同じ起動で `TPM2_Shutdown` のRPC待ちを採取し、145秒でタイムアウトした。
  元のコードは現在のドメインの `assigned_harts` でIPIの宛先を絞り、
  同期OP-TEE呼出し中のhartはLinux側のマスクから一時的に外れる。
  このため、Linuxのタスク起床などに使うIPIを、当該hartへ送れない窓があった。
- 修正はLinux側の通常割当てと、一時的にOP-TEEを実行する呼出元hartのマスクを
  同じロック下で更新する。LinuxのSBIソフトウェアIPIには専用のイベントを
  使用し、宛先hartがOP-TEEを実行中なら保存済みLinuxコンテキストのSSIPに記録する。
  Linuxへ戻るときは既存のCSR復元でSSIPが反映される。HSMによる宛先の稼働状態確認は
  引き続き適用する。RFENCEとHALTは従来の宛先選定を使う。
- 16 hart K3 QEMUで、修正ファームウェアを使ったfTPMの4回の反復が
  モジュール登録、`/dev/tpmrm0` 経由の `TPM2_GetRandom(16)`、電源断まで成功した。
  診断出力を加えた別の試行では、hart 13でLinux宛てSSIPの保持を観測し、
  同じ試行でTPM応答と電源断に成功した。診断なしの最終ファームウェアと
  標準の試験用initramfsでも、TPM応答と電源断を確認した。
  既存の同居回帰試験では、別hartで実行中のKeystone EnclaveとOP-TEEの
  検証用TAが両方完了し、電源断した。過去のすべてのタイムアウトが
  同じIPIによるものかは未確認。実機試験は実施していない。

#### 過去のタイムアウトの証拠確認

保存されていたKSB-084のタイムアウト7件を、UARTと採取済みのスタックで照合した。
秒数はホスト側の試験制限で、各RPCの待機時間の計測値とは区別する。

| 保存ログ | 制限 | 確認できた停止段階 | IPIの証拠 |
| --- | ---: | --- | --- |
| `qemu-tpm-timeout.log` | 180秒 | TAロード後、TPM合格出力の前まで | 宛先や配送結果の記録なし |
| `qemu-tpm-diag.log` | 300秒 | TAのストレージ呼び出し、TPM合格出力の前まで | QMPでhart状態を採取。対象IPIの宛先判定の記録なし |
| `ksb084-original-pressure.log` | 120秒 | TAのストレージ呼び出し、TPM合格出力の前まで | 宛先や配送結果の記録なし |
| `ksb084-3.log` | 105秒 | TPM合格後、`TPM2_Shutdown` のRPC応答待ち | RPC待機スタックあり。対象IPIの記録なし |
| `ksb084-4.log` | 105秒 | 登録時のTPMプロパティ取得でRPC応答待ち | RPC待機スタックあり。対象IPIの記録なし |
| `ksb084-threads.log` | 145秒 | 登録時のRPC応答待ち | PID 1とsupplicantのスタックあり。対象IPIの記録なし |
| `ksb084-ipi-before.log` | 145秒 | TPM合格後、`TPM2_Shutdown` のRPC応答待ち | OP-TEE実行中のhart 1への送信を観測。IPIとRPCの要求IDの対応は未採取 |

最後のログのIPI診断は宛先マスク取得前のアクティブドメインを表示する。
ログから当該IPIが実際にマスクから除外されたか、停止したRPCを起床させるIPIだったか
までは判定できない。修正前の宛先選定に欠落する経路があることはコードで確認でき、
修正後の診断試験ではLinux宛てSSIPの保持を実測した。過去の7件すべてについて
個別に同じ原因を確定するための記録は残っていない。

標準のfTPM用initramfsで、ファームウェアだけを入れ替えて追加比較した。
16 hart・2 GiBのK3 QEMUで各1回、145秒制限を適用した。修正後・修正前ともに
`/dev/tpmrm0` で `TPM2_GetRandom(16)` が成功し、27秒で正常終了した。
この比較の2回ではタイムアウトは発生しなかった。

この実行環境にはJupiter2のUSB・UARTデバイスが見えておらず、接続先も
確認できなかった。KSB-084修正版による実機起動とfTPMは未検証。

#### KSB-084修正後のKeystone回帰試験

16 hart同居QEMUでQEMU用OP-TEEとKSB-084修正版OpenSBIを使用した。
SBIエラー検査、STOP/RESUME、乱数、crypto未対応構成、edgecall 2 MiBと
256 MiB、およびrobustnessのlifetimeは成功した。

- FID 4000/2006では不正引数検査とドライバーの所有権・失敗時cleanupが
  成功した。正常経路は同居構成のKeystone用PMP枠が5個の状態で、複数の
  enclaveを作る途中に `No available PMP register` とCREATEエラー
  `100003` が出て失敗した。この条件で総合ゲスト試験は終了値1だった。
- robustnessの2 worker・4 cycle試験では並行CREATEの一方がSBI `-10` を
  返した。複数回観測したが、KSB-043で記録したDESTROY失敗との同一性は
  確定していない。
- 現行ソースから `KEYSTONE_VERIFICATION=1` を再ビルドすると、PMP IPI
  transportが従来の2引数のHSM関数を呼ぶ箇所でコンパイルが停止した。
  従来の関数を復元し、Linux向けソフトウェアIPIの追加宛先を扱う経路に
  拡張関数を分けた。検証用SMの30 translation unitとOpenSBIのリンクまで成功した。
- DESTROY競合とclose遅延解放の既存fixtureは、最初のDESTROYが成功して
  `-EAGAIN` の判定に到達しなかった。今回の通常ファームウェアでの実測では
  競合経路の成功を確認できなかった。

#### 不合格項目の再試験

- CREATEとCREATE_V2は、SMが更新処理に入る前に返すSBI `-10` だけをLinux側で
  最大1秒再試行する。期限に達したときは `-EAGAIN` を返す。
  診断用ドライバーでは、同居構成で16回再試行したCREATEの成功を観測した。
  元の2 worker試験は、同居構成で `-10` に代わりPMP枯渇 `100003` が出た。
  Keystone単独構成での並行試験もPMP全hart更新の失敗で完走に至らなかった。
  backingなしの診断試験ではCREATEの再試行後の成功を2件観測した。
  一方のworkerは明示DESTROY後に失敗し、cleanupのDESTROYが
  `-EAGAIN` を返した。試験全体は終了値1。
- 同一Enclaveを対象にした直接SBI試験は、DESTROY同士の一時競合に
  `-10` を期待するよう更新した。検証用SMを使った16 hart QEMUで
  RUN／RESUME／DESTROYの9組すべてに合格した。
- Linuxサンプル試験のUARTに `/dev/kmsg` の合格行を出すため
  `printk.devkmsg=on` を追加した。一律PMPと混在PMPの両方で
  CPU 3・8上の `hello` と `hello-native` が終了値0と明示DESTROYを返した。

### KSB-085: 並行CREATE／DESTROY時に全hart PMP更新が失敗する

- 16 hart・Keystone用PMP 5枠の同居QEMUで、backingなしの2 workerを
  CPU 0・1に固定した。各workerは別Enclaveで4周のライフサイクルを実行する。
  診断用ドライバーはCREATE再試行回数を表示し、診断用テストはDESTROYの
  `-EAGAIN` を再試行する。
- 修正前に `pmp_unset_global` が失敗した試行では、QMPでhart 1のPCが
  `sbi_hart_hang`、戻り先が `context_switch_to_enclave` 内の停止呼び出し直後、
  `a0=-10` であることを確認。そのhartのM-mode外部割り込みもpendingだった。
  切替時の `k3_keystone_pmp_assert_active()` は、全hart PMP更新の送信者が握る
  HSMゲートと競合すると `-10` を返す。宛先hartが停止し、送信側はACKを得られなかった。
- PMPポリシーがACTIVEまたはTRANSITIONで、HSM Startが進行していなければ、
  ローカル切替はポリシーロック下で状態を確認する。これらの状態はすでに
  新規HSM Startを拒否する。TRANSITIONを保持し、起動時に状態を設定する経路では
  従来どおりHSMゲートを使う。
- この修正だけで実行した試行には、停止せずに全hart更新が不合格となる例もあった。
  追加診断で、hart 3のACK待ちが524,202タイマーティック（24 MHzで約21.8 ms）
  で終了し、その直後に読んだメールボックスがDONEだった。固定100万回の
  ポーリングを、ACK確認区間全体で100 msの実時間期限に変更した。
  世代一致、受信側でのPMP読み戻し、失敗時の保護を引き続き適用する。
- PMP枠の枯渇は別の拒否条件。たとえばEPMとUTMとbackingを1枠ずつ使う
  Enclaveを2つ保持するには6枠必要で、5枠の構成ではCREATEを拒否する。
  EPM/UTMの枠割り当て失敗時に出るSBIの `100003`
  （`SBI_ERR_SM_ENCLAVE_PMP_FAILURE`）は、既存のエラー契約。
- 2件の修正を適用した診断用並行試験は5回中4回成功。backing付きの
  元の試験では、再ビルド後も5枠に収まらないCREATEをSBI `100003` で
  拒否した。別起動の `/dev/tpmrm0` の乱数取得と正常電源断も確認した。
- 100 ms期限の診断ビルドでも、送信元hart 1からhart 0への解除要求が
  2,488,587ティック（約103.7 ms）でPENDINGのまま残る別の試行があった。
  その後のQMPでhart 0はLinuxのidleにいて、M-mode外部割り込みはpendingで
  なかった。期限超過時の状態を確認できたが、IPIが配送されなかったのか
  宛先が処理する前に期限に達したのかは未確定。
- 約21.8 msはACKループ中のゲストタイマー経過。ループ内のデバッグ出力は
  なく、診断行はタイマー値を採取した後に出した。QEMUのスケジューリング
  待ちとゲスト内処理時間の内訳は未計測。
- 100 ms期限の別試行で、送信側がPENDINGのまま失敗を返した後に、
  QMPで宛先hart 1のメールボックスがFAILED、PCが `sbi_hart_hang()`
  となったことを確認した。CREATEの失敗処理は、遅れて動く受信側が参照する
  PMP記述子を先に解放していた。PMP更新が不確定のまま終わったCREATEと、
  作成後半のロールバックでPMP解除に失敗したCREATEは、記述子とEIDを保持する。
  新しいSBI結果 `100017` とEIDをLinuxドライバーに返し、ドライバーは
  `-EIO` として呼び出し元に通知する。DESTROYやcloseで対象ページは再利用されない。
  この回復不能経路の確認には、対応したSMとドライバーを組み合わせる必要がある。
- 更新後の通常ファームウェアとドライバーの組み合わせで、backingなしの
  2 worker・各4周の並行試験が3回とも完走し、正常に電源断した。
- 診断用SMで、最初の実IPI送信後に送信側の失敗を返した。Linuxドライバーは
  ページ保持をログに出し、CREATEは `-EIO` で終了した。その後のDESTROYも
  SMで拒否され、ゲストは正常に電源断した。診断用の失敗注入は製品コードに含めない。
  この試験は失敗後の処理を検証するもので、自然発生したACK遅延の原因は未確定。


### KSB-086: fTPM同居QEMUでEnclaveのCREATEが間欠的に失敗する

- eFuse有効のOP-TEE Core、Linuxの `tpm_ftpm_tee`、Keystoneを載せた
  16 hartのJupiter2 QEMUで、3起動中1回、EnclaveのCREATEが失敗した。
  fTPMのテストコマンドを発行する前に、全hartへのPMP更新が未完了となった。
- 追加診断では、送信元hart 2の最初のPMP更新で、宛先hart 3、7、14が
  別々の起動でPMPメールボックスをPENDINGのまま残し、100 msでタイムアウトした。
  各宛先に未完了のRFENCEが1件あった。キューも調べた別の再現では、
  hart 6のPMP ACKをhart 2が待つ間に、hart 6のRFENCE要求が
  hart 2の処理キューに残っていることを確認した。
- RFENCEを発行したhartは、M-mode割り込みを受け付けずに応答を待つ。
  PMPの送信元が自分宛てのRFENCEをキューに残したままPMP ACKを待つと、
  宛先もRFENCE待ちから戻れず、PMP IPIを処理できない。
- 修正コミット `8299c7faf` では、PMP ACK待ちの間に送信元hartのRFENCE
  キューを既存のOpenSBI処理で1件ずつ進める。100 msの期限、世代一致、
  PMPの読み戻し、失敗時の状態保持も引き続き適用する。
- 修正済みファームウェアの16 hart QEMU試験は5起動すべてで合格した。
  Linux CPU 3から `/dev/tpmrm0` 経由で `TPM2_GetRandom(16)` を実行し、
  CPU 2のEnclaveで各起動4〜7回のタイマー割り込みをTPMコマンドの送受信中に
  観測した。いずれもEnclaveの終了と破棄、およびゲストの電源断を確認した。
- 同じ修正済みファームウェアで、backingなしの2 workerが各4周の
  ライフサイクルを実行する並行CREATE／DESTROY試験も1起動で合格した。
- 初回の失敗ログにはRFENCEの診断情報が無いため、その1件およびKSB-085の
  過去の失敗が同じ待ち合わせだったかは未確認。実機は未検証。


UART抜粋は、[初回の3試行](evidence/jupiter2-ksb086/01-initial-uart.log)、
[再現診断](evidence/jupiter2-ksb086/02-diagnostic-uart.log)、
[修正後の同居・並行試験](evidence/jupiter2-ksb086/03-fixed-uart.log)、
[KSB-084・085の回帰試験](evidence/jupiter2-ksb086/04-prior-regression-uart.log)
に記録した。


### KSB-087: fTPMの永続化失敗時にNV_Writeが成功を返す

- KSB-086修正済みの16 hart同居QEMUで、稼働後に `tee-supplicant` を停止した。
  NV_Writeは成功を返したが、OP-TEEはストレージRPCの失敗を記録し、
  評価用REE FSのファイル内容は変わらなかった。
- supplicant再起動後、NV_Readは未保存の値を返した。再起動後の別の
  NV_Writeも成功を返したが、REE FSのファイル内容は変わらなかった。
- 原因は、採用したfTPM TAの既存のNVエラー処理にある。該当処理は
  採用元コミット `6f99e783eb9b` に含まれ、QEMU試験で使用した
  `platform/NVMem.c` に採用元からの差分がないことを確認した。
  Jupiter2への移植環境では、supplicant停止でこの既存の問題が顕在化した。
- 使用したfTPM版 `6f99e783eb9b` の `platform/NVMem.c` では、
  `_plat__NvWriteBack()` がエラー時に `s_NVInitialized` を解除して戻り、
  `_plat__NvCommit()` は成功を返す。この経路により、失敗が呼び出し元に伝わらず、
  以後の書き戻しも止まる。修正と再試験は未実施。
- [試験条件と結果](jupiter2-ftpm-ta-test.md#tpmコマンドと障害復旧)。
  [UARTログ抜粋](evidence/jupiter2-ftpm-recovery/uart.txt)。

### KSB-088: OP-TEE同居試験の入力ファイルが揃わない

- 症状。Keystone統合試験後、ランナーは `Missing OP-TEE test input:
  .build-k3/optee-coexist/boot.dtb` を報告した。同居ゲストは起動していない。
- 原因。Coreビルドは `tee.elf` までを生成する。DTBとinitramfsは試験環境で
  個別に用意され、リポジトリから作る手順と入力ソースが揃っていなかった。
  このログからOpenSBIのドメイン切替やTAの実行失敗は観測されていない。
- 対処。試験で使ったQEMU向け同居DTBの構成をDTSとして保存し、検証用の
  `/init` とともに、DTBとinitramfsを生成するスクリプトを追加した。
  採取済み実機DTBはQEMU構成の比較資料として扱う。
  [生成・試験手順](../verifications/optee-coexistence/README.md#keystoneの統合試験に同居試験を追加)
- 検証。新しいスクリプトで生成した2ファイル、検証用TA入りの既存Core、
  対応するLinuxとKeystoneドライバで、Sstc有効の同居ゲストを起動した。
  Linuxの16 CPU起動、Enclave実行16回、OCALL中を含むTA呼び出し33回、
  正常な電源断とQEMU終了コード0を確認した。
  利用者の環境での全試験と、今回のログにあるWTM乱数ケースは未再検証。

### KSB-089: OP-TEE同居ゲストの /init が命令アクセスフォルトで停止

- Linux 6.18.3 #4ではOP-TEEドライバの初期化後、PID 1の最初の命令
  （仮想アドレス `0x1071c`）で命令アクセスフォルト（`cause=1`）が発生した。
  提供されたinitramfsの `/init` はRV64静的ELFで、同アドレスは実行可能
  セグメント内のエントリポイントだった。
- 同居用DTSでは `0x181e00000` から2 MiBをOpenSBI側で実行不可としていたが、
  Linuxの `reserved-memory` に対応する定義がなかった。通常ページの
  割り当て対象に入らないよう、既存DTB生成スクリプトと同じ `no-map` 予約を追加した。
  報告時のフォルトの物理アドレスは未取得で、予約漏れとの因果は未確定。
- 修正後のDTBを使ったSstc有効のQEMU回帰では、Linuxによる2 MiBの予約、
  16 CPUの起動、Enclave実行16回、TA呼び出し33回、正常電源断と終了コード0を
  確認した。以前の合格試験用のLinux Image・ドライバを使用したため、
  報告時のImageとinitramfsを組み合わせた再試験は未実施。

### KSB-090: 既定の同居DTBでfTPMデバイスが作られない

- IMA試験で、過去に使用したDTBでは早期登録が成功した。同じ試験部品で
  既定の同居DTBに切り替えると、LinuxとOP-TEEドライバは起動したが、
  `/dev/tpmrm0` が作られず、IMAの早期ヘルパーは終了状態256を返した。
  2種類のOpenSBIバイナリで同じ結果だった。
- 既定のDTSにLinuxのfTPMドライバが照合する `microsoft,ftpm` ノードが
  なかったため、過去のfTPM試験用DTBと同様にノードを追加した。
  `make optee-coexist-test` で `boot.dtb` を再生成する。
- 別途報告されたUART出力0バイトのタイムアウトはこの比較試験では再現しておらず、
  同じ原因とは確認できていない。

### KSB-091: fTPM・IMAゲストの初期化がタイムアウトする

- fTPMノードを追加した同居DTBで、LinuxとOP-TEE初期化ログの後に早期登録が
  タイムアウトした。固定DTSには `/chosen/rng-seed` がなく、カスタムDTBを
  指定した場合のQEMUはそのプロパティを新規作成しない。
- ランナーがDTBをケースごとにコピーし、ホストの `/dev/urandom` から
  32バイトを取得して `rng-seed` として渡す。元のDTBは保持する。
- 報告されたUART出力0バイトのタイムアウトとは停止段階が異なる。
- 修正版では以前の試験用OpenSBIを使い、早期登録26秒・遅延登録25秒で
  両方のPCR検査と電源断に成功した。別のローカルOpenSBIでは早期登録は
  合格したが、遅延登録はOP-TEEのストレージ処理に入った後に100秒で
  タイムアウトした。

### KSB-092: 実機の同居RAM起動でOpenSBIのドメイン初期化が停止する

Jupiter2 Pico-ITXのUSB RAM起動で、統合FITの転送とESOS両コアの応答後に
`sbi_domain_finalize: platform domains_init() failed (error -3)` が出た。
U-BootとLinuxへは到達していない。影響範囲は実機のKeystone・OP-TEE同居構成。
原因および上流との関係は未確定。

`opensbi/lib/utils/fdt/fdt_domain.c` に、失敗したドメイン名と処理段階の
出力を追加した。継承時に領域数の上限に達した場合は、DT指定数、継承済み数、
上限、次のroot領域を表示する。既存の領域上限とアクセス権限は維持する。
Keystone構成の `fw_dynamic.elf` と `fw_dynamic.bin` は再リンク済み。
診断版の統合FITの生成と実機での診断ログ取得は未実施。

診断版の実機ログでは、`untrusted-domain` のDT指定7領域と継承済み9領域で
従来の上限16に達し、次のroot領域（`0x100200000`、2 MiB）を追加できなかった。
DT指定分と継承分を先に数え、終端を含む配列を必要数で確保するよう修正した。
保護領域とPMPの割り当て規則は維持した。Keystone構成のOpenSBIは再リンクに成功。
修正版の実機起動、PMP割り当て、Keystoneの空き枠は未確認。

修正版の実機ログでは両ドメインの登録を通過した。hart 0のPMP設定はGEUの
1 KiB領域を4 KiB粒度で表現できず `-2` で停止した。実機用DTB生成では、
K3 OP-TEEの既存MMIOマッピングに合わせてGEUを `0xf0702000` の4 KiBページとする。
権限はOP-TEEに読み書き、untrusted-domainに拒否を維持する。
DTB生成と領域指定は確認済み。FIT再ビルドと修正版の実機起動は未確認。

GEUの4 KiB化後の実機UARTでは、MPXYのOP-TEEディスパッチャ初期化で
`K3 OP-TEE PMP: fixed slot plan rejected (-2)` が最初に出た。
参考構成に追加した同居領域を現行のK3固定枠へ割り付ける前提が成立していない。
通常枠はログのhostドメイン19領域から全域許可と既存のファームウェア領域統合を
引いて17枠相当で、Keystoneを含む現行計画の上限は12枠。
generic MPXY初期化は個別ドライバの失敗を起動側へ返さず、その後の
hart 0のPMP初期化でも失敗し、S-modeへは到達していない。
PMP配置の修正と再試験は未実施。

#### 実機用DTB生成の見直し

`d072a8b26` の生成処理はCore、共有メモリ、U-Boot FDT、GEU、PMU MAIN、
PMU APをすべてホスト側の明示領域として登録する。最新UARTではホスト19領域から
全域許可1件と既存のOpenSBI領域統合1件を除いて通常17枠相当となる。
通常枠の上限12に対し、PMU APの同一範囲を仮に1枠化できても通常16枠相当が残る。

K3版OP-TEEのソースではeFuseを有効にするとGEUに加えPMU MAINとPMU APを
マッピングする。PMU APは実機rootから継承されるM-mode専用範囲にも現れるため、
範囲の一致だけで規則を除去できない。ホスト側のU-Boot FDTと共有メモリも、
全域許可との差だけで判断すると、OP-TEE側の権限を設定する専用スロットを失う。
現行の切替実装はホストとOP-TEEの範囲およびMMIO属性が一致することを要求する。
現時点では権限を維持したまま12枠に収まるDTB単独変更を確認できていない。

#### 共通16枠での状態別割り当ての検討

実機rootの14領域は、既存のファームウェア保護の統合を適用すると通常12枠と
末尾の全域許可1枠に相当する。残り3枠はKeystoneのOS全域制御、EPM、UTMに必要。
OP-TEE側だけで必要になる権限のためにホスト側の明示領域を予約する現行実装では、
この配置に同居用の追加領域が収まらない。

状態ごとに枠を使い直す場合でも、Linuxが動く間はOP-TEE Coreへのアクセスを
継続して拒否する必要がある。起動時FDTのOP-TEE向け読み取り許可や、
共有メモリの明示枠をOP-TEE実行時だけに移しても、このホスト側の不足は残る。
既存のロック済みESOS領域は状態切替に使えない。
PMU APは継承されたM-mode専用範囲と重複しているため、両側の実効権限を
確認できるまで共有枠には数えない。rootが明示的に許可する
RPMI関連ページ `0xd4017000` も、EnclaveのOS全域拒否より前に評価される
既存規則との等価性を検証する対象とする。

現段階で成立を確認できたのはKeystone単独の枠構成。実機同居の16枠表は未確定。

#### Keystone単独で通過した実機の枠

Keystone単独のUARTにある領域の順序、OpenSBIマスク `0x8fff`、
Keystoneマスク `0x7000`、ファームウェア保護のslot 7統合から再構成した。
下表の権限は当該エントリのS/U権限で、各アドレスの最終権限は先に一致する枠で決まる。

| 枠 | ベース | 範囲 | S/U権限 |
| --- | --- | --- | --- |
| 0 | `0xcac90000` | 4 KiB | 拒否 |
| 1 | `0xd4017000` | 4 KiB | RW |
| 2 | `0xd4282000` | 4 KiB | 拒否 |
| 3 | `0xf1800000` | 16 KiB | 拒否 |
| 4 | `0x100800000` | 16 KiB | 拒否 |
| 5 | `0xf1000000` | 64 KiB | 拒否 |
| 6 | `0xf1810000` | 64 KiB | 拒否 |
| 7 | `0x100000000` | 1 MiB | 拒否 |
| 8 | `0x100d00000` | 1 MiB | 拒否、ロック |
| 9 | `0x100200000` | 2 MiB | 拒否、ロック |
| 10 | `0x100400000` | 2 MiB | 拒否、ロック |
| 11 | `0x100800000` | 4 MiB | 拒否、ロック |
| 12–13 | 実行時に設定 | EPM・UTMの最低2枠 | Keystoneが設定 |
| 14 | 全域 | Keystone OS全域制御 | Keystoneが切り替える |
| 15 | 全域 | OpenSBIの末尾規則 | RWX |

枠4は枠11に含まれるが、枠11はロック設定を持つ。枠4を削ると、
この16 KiBで先に一致する規則が変わるため、S/U拒否の一致だけでは同等と判断できない。
枠1のRWもEnclave実行時の全域拒否より先に評価されるため、ホストの全域許可だけで
置き換えられるとは確認できない。現在のCore配置 `0x171000000` は既存の拒否範囲外。
既存のロック・優先順位とKeystoneの最低3枠を維持する条件では、
現行の枠にCore保護を追加できない。枠を空けられる等価変換は未確定。

#### 実機のMMIO・共有領域7枠の内訳

販売元Pico-ITX DTBとOpenSBIの登録経路を照合した。
以前「追加MMIO」としていた `0xf1810000` は販売元DTBのCLINTである。

| 枠 | ベース、サイズ | 用途と削減の判定 |
| --- | --- | --- |
| 0 | `0xcac90000`、4 KiB | RPMI doorbell。mailbox群を既に1ページにまとめている。 |
| 1 | `0xd4017000`、4 KiB | UART。S/U読み書きを許可する。削除すると後段の全域規則に依存し、状態ごとの権限が変わる。 |
| 2 | `0xd4282000`、4 KiB | K3レジスター保存領域。M-modeの処理が参照する。OP-TEE側のPMU APと同範囲。 |
| 3 | `0xf1800000`、16 KiB | M-mode APLIC。 |
| 4 | `0x100800000`、16 KiB | RPMI共有キュー。後段のESOSロック領域に含まれ、先行規則でM-modeからのアクセスを維持する。 |
| 5 | `0xf1000000`、64 KiB | M-mode IMSIC。 |
| 6 | `0xf1810000`、64 KiB | CLINT。実機起動ではACLINTタイマーとして使用する。 |

APLICとCLINTを1個のNAPOT領域にまとめると、間の48 KiBもS/U拒否の対象になる。
同範囲に他のノードが見当たらないことだけでは、予約穴と実効権限の等価性は確定しない。
現行の実効権限を維持したまま削減できる枠は未確定。

#### UART枠の削減可否

OpenSBIの8250ドライバはUARTページをrootにM/S/Uの読み書き許可として登録する。
同居ドメインへの継承対象はS/U権限のないroot領域なので、実機UARTログの
`untrusted-domain` には `0xd4017000` が現れない。したがってrootのUART規則を
取り除いても、今回17枠相当になったホスト側の計画は減らない。

K3版OP-TEEは `CFG_RISCV_SBI_CONSOLE=y`、`CFG_16550_UART=n` で、
コンソール出力をOpenSBIに委ねる。Keystone単独のrootでは、UARTの明示RWを
外すと通常ホストは全域許可のRWX、Enclaveは先行するOS全域拒否に従う。
これらはPMP上の権限の違いであり、MMIOに対する実機PMAの挙動は未検証。
今回の同居PMP不足に対する削減枠としては数えない。

#### APLICとCLINTの統合可否

販売元U-Boot DTBではAPLICが `0xf1800000–0xf1803fff`、CLINTが
`0xf1810000–0xf181ffff`。OpenSBIの登録処理では両方ともMMIO、M-mode RW、
S/U拒否。採取済みのLinux DTBと `iomem.txt`、K3 DTS、OpenSBIソースを
照合したが、間の `0xf1804000–0xf180ffff` が予約領域と断定できる資料はない。
1個のNAPOT枠にすると `0xf1800000–0xf181ffff` の128 KiBになり、
この48 KiBにもS/U拒否がかかる。既存の実効権限を維持する条件では統合を採用しない。
仮に統合しても、ホスト側の通常枠の要求は17から16となり、上限12に対して4枠不足する。

#### Core・GEU・PMU MAINの既存保護との照合

実機UARTのroot領域一覧では、Core `0x171000000`、GEU `0xf0702000`、
PMU MAIN `0xd4050000` は、どれも既存の個別拒否領域に含まれない。
末尾の全域許可を維持する現在のホスト方針では、これらの拒否が必要な限り、
OP-TEEへの切替時だけ枠を用意する方式では代替できない。
K3版OP-TEEはeFuse有効時にGEUと両PMUをマッピングする。

ホスト側でFDT専用枠を省ける切替方式と、PMU APの重複を解消できたと仮定しても、
共有メモリの実行禁止を残すなら通常17枠から15枠。この時点で上限12まで3枠不足する。
共有メモリの実行禁止を別の既存規則で維持できる根拠は未確認。
既存root領域での単純な代替は成立せず、コード変更・起動試験は未実施。

#### ホストの許可範囲とKeystone枠の状態別利用

採取済み `iomem.txt` では、RAMのほか、PCIe、USB、UFS、UART等が複数の
アドレス範囲に分散する。現行計画は全域許可1枠を必須とし、これを個別の
RAM・MMIO許可へ置換するにはKeystoneのホスト復帰と末尾枠の規則も見直す必要がある。
採取資料から、既存のアクセス要件を満たす16枠の許可リストは確定できていない。

別の候補としてKeystoneのOS全域制御枠14をホスト中のOP-TEE Core拒否に
再利用できるか検討した。現行のホスト状態で枠14と15は全域許可であり、
代替には枠14のホスト時の意味とCSR検査・復帰規則の変更が必要。
Enclave状態では枠14が全域拒否を担当し、EPM・UTM・バッキングの先行設定は
OP-TEE範囲との重複検査を維持する。静的にはCore専用枠1個の削減候補。
FDTとPMU APの整理も成立すると仮定した場合、通常15枠から14枠相当となるが、
GEUとPMU MAIN等を含む配置全体は上限12をなお超える。未実装・未試験。

#### Secure AIAの統合を含む共通16枠案

SpacemiTのアドレスマップで `0xf1000000–0xf7ffffff` がSecure AIAの窓と確認した。
M-mode用のIMSIC・APLIC・CLINTを `0xf1000000–0xf1ffffff` の1枠にすると2枠減る。
採取済みLinux DTBのIMSIC・APLIC・SSWIはこの範囲の外側にある。全域規則の統合、起動時FDTの
Core内への複製、PMU APの既存枠を使ったM-mode仲介と合わせて、13固定枠、2 Keystone枠、
1全域枠の配置を静的に検算した。ESOSの4つのロックと、それより優先するRPMI共有キューを維持する。
PMU MAINと公開eFuse値にはLinuxのアクセス経路が必要であり、QEMU・実機試験は今後行う。
[共通16枠案と検査条件](keystone-optee-coexistence-design.md#10-secure-aiaをまとめる実機用16枠案)

同梱FITのCoreにはRTC、TE200、PRNG、IOPMPも含まれていた。Linux側のSecure AIAと周辺装置を
1枠で拒否してI²C3を先行規則で許可し、実行状態ごとに枠を切り替えると、既定機能を有効にする
CPUのPMP配置も最大16枠で表せる。クロック・リセットの仲介とIOPMPの実効権限の確認が残る。
[既定機能を維持する枠の表](keystone-optee-coexistence-design.md#103-実機のop-tee既定機能を維持する割り当て)

#### QEMUでの全域枠共用の確認

同居時に通常枠13個を使う構成では、OpenSBIとSMが全域枠15を共用するようにした。
枠13・14をEPMとUTMに割り当て、Enclaveへの移行時には全域規則を先に閉じ、ホスト用の
個別許可も解除する。Linuxへ戻る際は個別規則を復元した後に全域許可を戻す。
OP-TEE起動後のセカンダリhartの停止は、全域枠を拒否にした状態でHSMへ進む。

16 hart・2 GiBのK3 QEMUで、4 KiB粒度の各hartのPMPを読み戻した。13通常枠の同居試験で
起動直後のLinuxは14枠、LinuxとOP-TEEの実行時は最大15枠、Enclave実行時は16枠だった。
混在構成では32枠を持つhartの上位16枠も無効だった。既定の同居構成も回帰試験に通過した。
通常枠を14個にしたDTBは、全域枠とKeystone用2枠を加えると17枠になるため、Linux起動前に拒否された。

切替前後の物理範囲と権限を受け取る共通処理を `opensbi/lib/sbi/sbi_hart.c` に追加した。
物理範囲を変更する場合は枠15を全域拒否にしてから対象枠を無効化する。書き込みを読み戻して検査し、
失敗時は切替前の設定を復元する。ロックを含む切替要求は書き込み前に拒否する。
追加後の回帰では、同じ物理範囲を使う混在16/32枠、一律16枠、従来DTBの同居試験と、
17枠が必要なDTBの起動時拒否を確認した。

次に、GEUの状態別アドレスをOpenSBIのK3用コードに定義した。混在16/32枠と一律16枠のQEMUで、
Linuxの16 KiB拒否、OP-TEEの4 KiB RW、Linux復帰後の拒否を枠7のCSRで確認した。
定義外の窓と範囲が重複するDTBはLinux起動前に拒否された。

Pico-ITXの全枠配置をK3コードに追加した。QEMUでは枠14をLinuxのDCIU拒否、OP-TEEの無効、
EnclaveのUTM RWで共用し、Linux復帰時の読み戻しを確認した。混在16/32枠と一律16枠で最大16枠だった。
Pico-ITX向けのFSBL・FIT・Linux DTBを生成し、Coreと予約範囲を照合した。
2026-11-28の実機USB RAM起動では全16 hartで起動時15枠、OP-TEE実行時14枠を読み戻し、
この問題で止まっていたOpenSBI初期化を通過した。Linux復帰後のPMPとDMA保護は未確認。
[実機で確認した範囲](jupiter2-coexistence-16-pmp-plan.md#pico-itx-ram-boot-2026-11-28)
[B案の選択とA案へ変更する条件](jupiter2-coexistence-16-pmp-plan.md#状態別pmpアドレスの定義先)
[QEMUのUART・CSR記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### KSB-093: 実機同居用のOP-TEE起動DTBが読み取り専用

実機用同居DTB生成では、U-Bootと起動時FDTを含む領域のOP-TEE権限を `0x08`（読み取り）にしている。
採用コミット `2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59` のK3構成は `CFG_EXTERNAL_DT=y` で、
OP-TEE起動時に `fdt_open_into()` を同じバッファーに対して呼び、`update_external_dt()` で
ノードと予約情報を書き込む。実機用生成側の権限指定と採用版の起動処理の不整合をソースで確認した。
初期調査では、起動が先にKSB-092の枠不足で止まり、この書き込みまで到達しなかった。
[実機用DTBの権限指定](../scripts/prepare-jupiter2-optee-opensbi-dtb.py#L40) · [OP-TEEの外部DTB初期化](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59/core/kernel/dt.c#L809)

OP-TEEのリンク時に書き込み可能な領域を確保し、OpenSBIが検査済みDTBを複製してCoreの起動引数へ渡す。
QEMUでは元のDTBをOP-TEEから読み取り専用にした状態で、コピーを使う初期化とTAの実行を確認した。
実機向けはELFとBINの一致、予約領域、FIT内のDTBをホストで照合した。
2026-11-28の実機ログでOpenSBIが66,352バイトの起動DTBをCore内に複製し、Coreが起動して
エントリーテーブルを登録したことを確認した。U-Boot本体への引き渡しはKSB-098で追跡する。
[実機UART抜粋](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ram-boot-uart.txt)
[OP-TEEの予約領域](../patches/optee/k3-private-boot-dtb.patch) ·
[QEMUとホストビルドの記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### KSB-094　MPXY初期化のエラーがK3 Keystoneの起動元に返らない

FDTのMPXYドライバーが初期化エラーを返しても、genericプラットフォームは成功として返していた。
K3 Keystoneでは、同居用のPMPや私有DTBの準備が確定する前に後続の初期化へ進む可能性があった。
K3 Keystone構成で初期化エラーを呼び出し元へ返し、S-modeへの引き渡し前に停止するようにした。
QEMUで容量が不正な私有DTBを指定し、`mpxy init failed (error -3)` で停止したことを確認した。
[MPXY初期化の呼び出し](../opensbi/platform/generic/platform.c)

### KSB-095　OP-TEE単独のQEMU並行TA試験で停滞

16 hartのK3 QEMUをマルチスレッドTCG、2 GiB、Sstc有効で起動した。syscon電源断を有効にした
OP-TEE単独用OpenSBIを使用した。Linuxの16 CPUとOP-TEEドライバーの初期化後、並行TAの試験中に
初回は `rcu_sched detected stalls` を出力し、80秒でタイムアウトした。

PMP枠調整前の `309f57738` から同じ設定でビルドしたOpenSBIのSHA-256は、当初の失敗時と一致した。
これと私有DTBバッファー追加前のCoreを組み合わせた試験も80秒でタイムアウトした。
初回の採取には停止時のレジスタがないため、同じ割り込みの連続を起こしたかは確認できていない。

#### 再現時の原因

- 通常ビルドの反復で、LinuxとOP-TEEを切り替える `switch_to_next_domain_context()` の
  `assigned_harts_lock` 待ちを複数hartで確認した。UARTが増えない間もロックの解放番号は
  35秒時点の3,709から55秒時点の5,022、73秒時点の6,154へ進んだ。
- このQEMUホストは16 vCPUに対してCPU時間の割当てが2 CPU分だった。試験Linuxの周期タイマーは
  250 Hzで、ドメイン切り替え中にも期限に達する。OP-TEEが保留中のタイマー割り込みを検出すると、
  `OPTEE_SMC_RETURN_RPC_FOREIGN_INTR` を返し、割り込みを処理するLinuxへ戻る。
- 診断用OpenSBIで、55秒までに試験が完了しなかった回のhart 0を40秒時点で採取した。
  209件のMPXY応答中204件が割り込み処理のための復帰で、その204件すべてで
  `mip.STIP` が立っていた。短い間隔で各hartが再試行すると、ドメイン切り替えが競合し、
  TA処理が進まないままタイマー割り込みによる復帰が繰り返された。

#### 修正

LinuxのMPXYドライバーで割り込み応答が連続した後に待機を加える試行では、待機時間を変えても
タイムアウトした。

K3のOP-TEE単独構成では、Linuxが再試行できるyielding呼び出しに限り、OpenSBIが切り替え元と
切り替え先の所属ロックを `spin_trylock()` で取得する。片方でも競合したら、取得済みのロックを
解放して `SBI_EINVALID_STATE` を返す。hartの所属とPMPは両方のロックを取得するまで更新しない。
LinuxのMPXYドライバーはこの結果を `-EAGAIN` に変換し、既存の期限付き再試行を使う。
fast呼び出し、OP-TEEからの復帰、Keystone同居構成ではロック取得を待って切り替える。
[OpenSBIのドメイン切り替え](../opensbi/lib/sbi/sbi_domain_context.c)
・[MPXYディスパッチャー](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c)

#### QEMU検証

同じQEMU・Linux・Core・DTB・initramfsを使った16 hartの反復試験は、修正前が4回中2回合格、
修正後が10回中10回合格。合格は全16 CPUのTA応答検査、ゲストの電源断、QEMU終了コード0で判定した。
修正後の実行時間は7.1〜9.0秒だった。

- 診断用の修正版では、切り替え元・切り替え先それぞれのロック競合で
  `SBI_EINVALID_STATE` を返したことをQMPで確認した。2回とも並行TA試験と電源断に成功した。
- 私有DTBバッファー追加前のCoreでも3回、Sstc無効に合わせたCPU設定とDTBでも2回、全回合格した。
- Keystone同居構成のPMP 16/32混在試験も合格した。16回のEnclave実行、OCALLを含む33回のTA呼び出し、
  電源断を確認し、各状態で使用したPMP枠は最大16だった。
- 単独構成の手順書に記載したQEMU起動コマンドを検証済みの成果物で実行し、合格を確認した。

実機での再現性と修正の効果は未確認。

[起動条件・試験記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)
[単独構成のビルド・試験手順](qemu-build-install-test.md#3-op-teeのみを使う)

### KSB-096 OP-TEE先行起動で副hartのPMP記録が失敗する

#### 発生条件と原因

16 hart、2 GiB、Sstc有効のK3 QEMU同居構成で、fTPM・IMA遅延登録用のゲストが
Linuxの起動前に180秒でタイムアウトした。初回のUARTでは、hart 4のPMP設定と読み戻しは
成功し、ほかの14副hartがOP-TEE初期化を完了した。初回のhart 4のレジスターは未採取。

初回UARTを再集計した。主hartのOP-TEE初期化完了後、15副hartすべてで
`configure-return Hart=... rc=0` が出ていた。Keystone SMの初期化完了は14件で、
OP-TEEの副hart初期化完了もhart 4を除く14件だった。停止区間はPMP設定完了からSM初期化完了まで。
KSB-097の拒否点は対象hartの起動前、KSB-083のHSM起動完了処理はSM初期化の後にある。
同じ詳細ログ付きOpenSBIでLinuxまで起動した48回は、すべてSM初期化完了の行を15件記録した。
初回の停止区間は、PMPの読み戻し結果を起動台帳に記録するときのKSB-096と最もよく一致する。
[副hartの起動順序](../opensbi/lib/sbi/sbi_init.c) ·
[SM初期化完了の出力箇所](../keystone/sm/src/sm.c)

同じCore、DTB、Linux、initramfsを使い、PMP詳細出力を無効にしたOpenSBIで起動したところ、
10回目でhart 3・8・9が停止した。起動から25秒と50秒のQMP採取を同じOpenSBI ELFと照合した。
3 hartとも `sbi_hart_hang()` に留まり、`sbi_hsm_k3_e2_note_local_snapshot()` が
`SBI_EDENIED`（`-4`）を返した状態だった。逆アセンブリと照合すると、ロック読み取り値は1で、
ロック取得に成功した場合に0となる `sc.w` の結果レジスターも1だった。
台帳のロックを取得できずに戻った分岐である。
主hartはOP-TEEの `wait_secondary` で待機していた。
この回ではLinuxのfTPM登録に到達していない。

K3 Keystone移植の起動台帳は、ロックが使用中だと即時にエラーを返していた。
PMPを検査済みの副hartが、その結果を台帳に記録する時点で別hartの更新と競合すると、
OpenSBIはその副hartの起動を打ち切った。KSB-083で対処した共有HSM/PMPゲートの取得より
前に通る処理である。詳細ログを有効にしてKSB-097のみ適用した版でも、ホストCPU 2個で
10回すべてLinuxまで起動した。初回のhart 4が通った分岐の確定には至っていない。
[起動台帳](../opensbi/include/sbi/k3_e2_hart_quarantine.h) ·
[S-modeへ移る前のPMP読み戻しと記録](../opensbi/lib/sbi/sbi_init.c)

#### 修正

起動台帳にはOpenSBIのチケットロックを使い、取得順に台帳の読み書きを行う。
ロックの範囲は台帳の短い更新と読み取りに限る。HSMの起動予約、ローカルPMPの読み戻し、
起動完了の順序と検査を維持する。台帳への記録を拒否した場合は、hart番号とエラーをUARTへ出す。
[起動台帳の実装](../opensbi/include/sbi/k3_e2_hart_quarantine.h)

[QEMUの入力と停止時の記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

### KSB-097 OP-TEEの副hart起動要求が共有ゲートの競合で失敗する

KSB-096だけを修正したOpenSBIで、5回は全16 CPUでLinuxが起動した。6回目は
`Error starting secondary hart 2` を出力して停止した。QMPの採取ではhart 2はOpenSBIの
HSM待機のままで、主hartはOP-TEEの `wait_secondary` に留まっていた。

起動要求側の拒否経路に診断を加えたビルドでは、6回目に `start gate busy for hart 4` と
`Error starting secondary hart 4` が出た。主hartが次の副hartを起動する間に、すでに
起動を要求されたhartもHSM起動完了を処理する。発行側は共有HSM/PMPゲートを取得できないと
`SBI_EINVALID_STATE` を返し、採用版OP-TEEは当該hartの起動を再試行せずに完了を待っていた。

初回の180秒停止と同じ詳細ログ付きの旧バイナリを、ゲスト16 hartのままホストCPU 2個に
割り当てて再試験した。3回目に `Error starting secondary hart 7` を出力し、
180秒で試験を終了した。25・55・120・165秒の採取で、hart 7はOpenSBIのHSM起動待機、
主hartはOP-TEEの `wait_secondary` に留まった。この回の停止点はKSB-097の診断と一致する。

修正版では、対象hartの初回起動またはOP-TEEからLinuxへの初回引き渡しに限り、
ゲートが空くまで既存の実時間ベースの待機処理で最大100 ms再試行する。待機は起動予約前に行う。
取得後に異常状態、起動予約、PMPの保護状態を検査し、期限内に取得できない場合は
起動要求にエラーを返す。この100 msはロックの取得期限であり、再現した回の保持時間は計測していない。
[OpenSBIのHSM起動経路](../opensbi/lib/sbi/sbi_hsm.c) ·
[Keystoneの共有ゲート](../keystone/sm/src/ipi.c)

#### KSB-096・KSB-097の修正後のQEMU検査

- 失敗を再現したときと同じCore、Linux、DTB、initramfsで40回起動し、全回でLinuxの
  16 CPU起動を確認した。起動反復ではその時点でQEMUを終了した。
- 初回の180秒タイムアウトと同じPMP詳細出力を有効にし、同じ入力でfTPM・IMA遅延登録を
  最後まで実行した。Linuxの16 CPU、IMA測定、PCR 10が変化しないこと、正常電源断を確認した。
  追加の反復でも通常のホストCPU割り当てで5回、ホストCPU 2個に限定して4回、全回合格した。
- 通常の `scripts/tests/jupiter2-ftpm-ima-qemu.sh` は早期・遅延の両方で合格した。
  早期登録ではPCR 10が独立計算したSHA-256値と一致した。遅延登録ではPCR 10が初期値を維持し、
  両方で `/ima-probe` の測定行を確認した。
- fTPMのNV試験は書き込み、別のQEMUプロセスでの復元、空のREE FSの対照試験すべてで合格した。
- Keystone単独は `hello` と `hello-native`、OP-TEE単独は全16 CPUの並行TA呼び出しが
  合格した。同居は各hart一律16枠・16/32枠混在ともEnclave 16回とTA 33回が合格した。
  PMP CSRから読んだ最大使用数は16枠で、32枠側の枠16–31は無効だった。

#### 公開コミットの再検査

修正コミット `777eef642` のクリーンなソースからOpenSBIとKeystone SMをビルドした。
既存のQEMU・Linux・OP-TEE Coreと各試験のDTB・initramfsを使用した。

- 初回と同じゲスト入力とPMP詳細ログを使い、ホストCPU 2個で遅延登録を4回実行した。
  全回で16 CPU、`/ima-probe` の測定行、PCR 10が変化しないこと、正常電源断と
  QEMU終了コード0を確認した。
- 一律16枠・16/32枠混在の同居検査は両方で合格した。各ゲストでEnclave 16回、
  TA呼び出し33回、GEUの枠切替と復元を確認した。PMP使用数の上限は16枠だった。

実機での確認は未実施。
[QEMUの入力と停止時の記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

<a id="ksb-098"></a>
### KSB-098 実機USB RAM起動でOP-TEE登録後のU-Boot出力が確認できない

2026-11-28のPico-ITXでの初回の同居USB RAM起動では、SPLのFIT受信、両RCPUのハンドシェイク、
OpenSBIのPMP初期化、OP-TEE Core起動まで到達した。最後の有効行は
`Registered OP-TEE entry table: 0x171000384`。この出力の直後に
`sbi_ecall_tee_domain_exit()` を呼ぶ。U-Boot本体のバナーやLinux起動ログは採取されていない。
カーネルモジュールの読み込みより前の段階である。

OP-TEEのセキュアストレージ鍵初期化では、eFuseバンク1・2が未書き込みと判定されHUK導出に失敗した。
その後もエントリーテーブルの登録まで進んだ。HUK導出の成否はストレージを試験する段階で確認する。
[到達した段階とPMPの実測値](jupiter2-coexistence-16-pmp-plan.md#pico-itx-ram-boot-2026-11-28) ·
[実機UART抜粋](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ram-boot-uart.txt)

#### 引き渡しの診断ログ

`b037d8266` に、PMP起動トレース有効時の起動hart向け診断を追加した。
エントリーテーブル登録後のドメイン選択、PMP切り替えの戻り値、hartの所属更新完了、
`sbi_hart_switch_mode()` への遷移、および `mret` 直前を記録する。
初回のドメイン終了処理から戻った場合は戻り値も表示する。
通常の `make opensbi` は `K3_PMP_BOOT_TRACE=1` を指定する。
[MPXYの初回完了処理](../opensbi/lib/utils/mpxy/fdt_mpxy_opteed.c) ·
[ドメイン切り替え](../opensbi/lib/sbi/sbi_domain_context.c) ·
[S-modeへの引き渡し](../opensbi/lib/sbi/sbi_hart.c)

診断版と同じQEMU入力で、変更前の混在16/32枠構成はLinux起動、Enclave実行、TA呼び出しと
電源断まで進んだ。診断版は混在16/32枠と一律16枠の両方で、登録後の5つの診断行が順に
出力された後、16 CPU、Enclave 16回、TA呼び出し33回、正常電源断を確認した。
診断版OpenSBIを含むPico-ITX用FSBL・統合FITとLinux用DTBをホストで生成し、bundle照合、
FSBLとFITの転送前dry-run、ホスト回帰48件に合格した。
[QEMUとホストビルドの証跡](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

#### 実機再試験で確認した原因と修正

提供された2026-11-28の再試験ログは、ヒープが106 KiBの構成で、
`Registered OP-TEE entry table` の直後に `K3 OP-TEE handoff: domain exit returned rc=-1004` で止まった。
`-1004` は `SBI_ENOMEM`。`sbi_domain_context_exit()` が初回切り替え用のhart別コンテキストを
確保できず、復帰先を選択する前に戻った。
[再試験の実機UARTとFITチェックサム](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ksb-098-retest-uart.txt)

同じ106 KiBを使った16 hartのQEMUでも同じ停止を再現した。失敗した要求は440バイトで、
連続した15,168バイトの空きデータ領域があった。QEMUで停止時の管理リストを読み取り、
OpenSBIが割り当てを記録する管理枠を使い切ったことを確認した。実機では管理リストの採取は未実施。
[OpenSBIのヒープ実装](../opensbi/lib/sbi/sbi_heap.c)

`617f1c388` でPico-ITX同梱FITのOpenSBI用DTBに、既存の `opensbi,config` の
`heap-size = <0x30000>`（192 KiB）を設定した。OpenSBIのELFと生成DTBから、
コード・データ・全hartのスタック・ヒープが既存の1 MiBのPMP保護範囲に入る配置かを検査する。
割り当て失敗時にはhart、ドメイン、要求バイト数、空きバイト数を記録する。
[DTB生成](../scripts/prepare-jupiter2-optee-opensbi-dtb.py) ·
[予約領域の検査](../scripts/build-jupiter2-reference-ram-boot.py)

192 KiBでは混在16/32枠と一律16枠のQEMUがともに16 CPUを起動し、Enclave 16回、
TA 33回（OCALLを含む）、電源断に合格した。使用したPMPは最大16枠。
ホストで生成した実機用FITはOpenSBIの実行時サイズ752 KiB、予約1 MiBで、同梱ファイルの
ハッシュ照合と転送dry-runに合格した。
[比較試験、実機用FITの生成とハッシュ](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

<a id="ksb-098-board-pass"></a>
#### 192 KiBの実機でU-Bootへの引き渡しを確認

2026-11-28の最後のUSB RAM起動では、SPLが2,624,105バイトの同梱FITを受信した。
OpenSBIのヒープは192 KiB、実行時サイズは752 KiB。OP-TEE Coreがエントリーテーブルを登録し、
hart 0が `untrusted-domain` へ復帰した。`PMP rc=0` と `mret` の出力に続いて
U-Boot本体のバナーと `=>` を確認した。KSB-098の停止点はこの実機試行で通過した。
[192 KiBの実機UART](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-ksb-098-192k-uart.txt)

この試行に続いて、UFSから同梱用のLinux Image・initrd・DTBを読み込み、Linuxの初期化を確認した。
副hartの起動失敗とwatchdog初期化のpanicは[KSB-099](#ksb-099)と[KSB-100](#ksb-100)で追跡する。
HUK導出エラーはこの試行でも出ている。セキュアストレージとfTPMはLinux起動後の試験で確認する。
[U-BootからLinuxを起動する手順](jupiter2-ram-boot-guide.md#coexistence-linux-boot) ·
[Linux上のKeystoneとOP-TEEの試験](milkv-jupiter2-stack-install.md#実機linux上でkeystoneとop-teeをテストする)

<a id="ksb-098-retest"></a>
#### 修正版の再生成とUSB RAM起動

同じ試験を再実施する手順。すでに修正版で `=>` が出ている場合はUFSの確認から続ける。
[UFSとLinux起動ファイルの確認](jupiter2-ram-boot-guide.md#coexistence-linux-boot)

1. 開発PCのリポジトリルートで修正版OpenSBIとKeystone SMをビルドする。
   K3用クロスコンパイラの設定は実機用ビルド手順の準備を参照する。
   [開発PCの準備](jupiter2-build-install-test.md#開発pcの準備)
2. 前回使ったOP-TEE Coreの`tee.bin`と`tee.elf`を用意する。
   以下は実機向けの標準出力先を使う例。別の場所にビルドした場合は両方のパスを合わせる。

```bash
git pull --ff-only && make opensbi JOBS=20
```

ビルドに成功したシェルで、統合FITの入力と新しい出力先を設定する。

```bash
SBI="$PWD/.build-k3/firmware/build-opensbi-k3-keystone/platform/generic/firmware/fw_dynamic"
TEE_BIN="$PWD/.build-k3/optee-hardware/out/core/tee.bin"
TEE_ELF="$PWD/.build-k3/optee-hardware/out/core/tee.elf"
OUT="$PWD/work/jupiter2-ram-boot/ksb-098-$(date +%Y%m%d-%H%M%S)"
VARIANT=keystone
test -s "$SBI.bin" && test -s "$SBI.elf" && test -s "$TEE_BIN" && test -s "$TEE_ELF"
```

3. 第1.5節で同梱FITとLinux用DTBを生成する。`VARIANT=keystone` で
   `--optee-elf "$TEE_ELF" --pico-itx-pmp16` が選ばれる。別PCへ運ぶ場合は第1.7節で包装する。
   [同梱FITの生成](jupiter2-build-install-test.md#optee-fit-build) ·
   [RAM起動用bundle](jupiter2-build-install-test.md#ram-boot-bundle)
4. FITの元になるOpenSBI用DTBで `heap-size` が `30000`（16進数）であることを確認する。
   同じ出力先の`FSBL.bin`と`ram-boot-keystone.itb`をUSB RAM起動の手順で転送する。
   UARTで `Firmware Heap Size : 192 KB`、`K3 OP-TEE handoff: PMP rc=0`、U-Boot本体のバナー
   または `=>` を確認する。電源投入から到達点までのUART全文と、使用したファイルのハッシュを保存する。
   [USB RAM起動手順](jupiter2-ram-boot-guide.md)

```bash
fdtget -t x "$OUT/records/opensbi-uboot.dtb" /chosen/opensbi-config heap-size
git rev-parse HEAD > "$OUT/records/ksb-098-source-commit.txt"
sha256sum "$SBI.bin" "$SBI.elf" "$TEE_BIN" "$TEE_ELF" \
  "$OUT/release/images/FSBL.bin" "$OUT/release/images/ram-boot-keystone.itb" \
  "$OUT/release/images/k3-pico-itx-keystone-optee.dtb" \
  > "$OUT/records/ksb-098-sha256.txt"
```

#### 最後のUART出力を読む

診断行は `K3 OP-TEE handoff:` で始まる。次の行が出ない場合は、上から順に到達点を判定する。

| 最後に出た行 | 次に調べる範囲 |
| --- | --- |
| `Registered OP-TEE entry table` | ドメイン終了処理の入口からコンテキストの確保・選択まで |
| `Domain context allocation failed` または `domain exit returned rc=-1004` | ヒープの設定値と、確保に失敗したhart・ドメインを確認する |
| `hart=0 target=... initialized=...` | 復帰先は選択済み。`PMP rc` が出るまでのPMP切り替え処理を調べる |
| `domain exit returned rc=...` または非0の `PMP rc=...` | 記録した戻り値と、その前に出た診断行 |
| `PMP rc=0` | hartのドメイン所属を更新する処理 |
| `domain assignment complete` | S-modeのコンテキスト復元と対象ドメインの起動判定 |
| `switch mode next=...` | `sbi_hart_switch_mode()` のレジスタ設定から `mret` 直前まで |
| `mret hart=...` | `mret` 直前まで到達。次は `mret` の実行とU-Boot入口から最初のUART出力までを調べる |
| U-Boot本体のバナーまたは `=>` | U-Bootへの引き渡しを確認。対応するDTBを使ったLinux起動へ進む |


<a id="ksb-099"></a>
### KSB-099 Pico-ITX同梱FITでLinuxの副hartがPMP検査に失敗する

192 KiB構成のUSB RAM起動でU-BootからLinux 6.18.3 #4を起動した。利用者は11月27日に使った
カーネルとモジュールを継続使用。ログ前半の通常起動では同じビルド表示のLinuxで16 CPUが起動した。
同梱構成ではLinuxのHSM起動要求に続き、hart 1〜15の全てでOpenSBIのPMP枠0が未設定
（`prot=0x0 addr=0x0 len=2`）と読めた。`K3 A1-E: root PMP readback failed` の後、
Linuxは副CPUごとに起動失敗を報告し、オンにできたCPUは0のみだった。
[実機UARTの抜粋](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-startup-uart.txt)

OpenSBIの`init_warm_startup()`は、OP-TEEの起動を終えて再開するhartで
`sbi_hart_pmp_configure()`を省略し、直後にLinux側のPMP配置を検査する。
実機のK3ではRPMI HSMの停止処理がコアまたはクラスタの電源断を要求する。
観測した未設定のPMPは、この経路で設定の保持を前提にした処理と一致する。
OP-TEE起動時に読み戻したPMP構成はKSB-098の記録にある。
[OpenSBIの再開処理](../opensbi/lib/sbi/sbi_init.c) ·
[K3の停止処理](../opensbi/platform/generic/spacemit/k3_corepm.c)

修正 `223c5f2` では、OP-TEE起動を終えたhartのHSM再開時にPMPを読む。
有効またはロックされた枠がなければ、既存の初期化処理でLinux側の配置を再設定する。
設定が残っている場合は、その内容を使って既存の全枠読み戻しを行う。
両経路とも従来のA1-E検査に合格してからS-modeへ渡す。
[再開とPMP設定](../opensbi/lib/sbi/sbi_hart.c) ·
[OpenSBIの事前検査](../opensbi/lib/sbi/sbi_init.c)

192 KiBのQEMU同居試験は混在16/32枠と一律16枠の両構成で、PMPが保持された副hart 1〜15の
再開を確認した。空のPMPで再開する条件はQEMU専用の検証ビルドで作り、LinuxのSMP起動中に
副hart 1〜15の再設定と `root-config PASS` を確認した。3件とも16 CPU、Enclave 16回、
TA 33回、最大PMP 16枠、正常電源断を確認した。修正版の実機起動は未試験。
[QEMUログと試験条件](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

<a id="ksb-099-retest"></a>
#### 実機の再試験

1. `git pull --ff-only` の後、開発PCで `make opensbi JOBS=20` を実行する。
   同じ実機用OP-TEE CoreのELF・BINと、新しいOpenSBIのELF・BINで同梱FITを新規出力先へ作る。
   [同梱FITの生成](jupiter2-build-install-test.md#optee-fit-build)
2. 同じ出力先のFSBLとFITでUSB RAM起動する。U-Bootから、前回と同じLinux Image、initrd、
   11月27日のモジュールを使う。Linux用DTBは同じFITビルドから生成したものを指定する。
   [UFSとLinuxの起動手順](jupiter2-ram-boot-guide.md#coexistence-linux-boot)
3. `smp: Bringing up secondary CPUs` 以降に副hart 1〜15の再開を確認する。
   PMPが消えていたhartでは `restore PMP on restarted hart` に続く `root-config PASS` を記録する。
   Linuxが `smp: Brought up 1 node, 16 CPUs` と表示し、watchdogの初期化を通過してログインできれば
   起動試験は合格。UART全文と使用したFSBL・FIT・Linux Image・initrd・DTBのSHA-256を保存する。
4. 同じ起動中に16 CPUのオンライン、TEEデバイス、Keystoneのサンプル、OP-TEEのTA呼び出しを確認する。
   [実機Linuxでの同梱試験](milkv-jupiter2-stack-install.md#実機linux上でkeystoneとop-teeをテストする)

<a id="ksb-100"></a>
### KSB-100 Pico-ITX同梱FITでwatchdog初期化が読み出し例外を起こす

同じ実機起動で、CPU 0がLinuxの初期化を続けた後、組み込みドライバの
`spa_wdt_probe+0xe4/0x47a`で`Oops - load access fault`が出てpanicした。
`Modules linked in:`は空で、呼び出し元は`spa_wdt_driver_init`だった。
[実機UARTの抜粋](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-startup-uart.txt)

レジスタの差分とドライバのソースから、読み出しは`mpmu_base + 0x1028`の`MPMU_ARSR`に
一致する。Pico-ITXのwatchdogノードが指定するMPMUの物理ベースは`0xd4050000`。
`0xd4051028`はPMPで保護されたMPMU内にあり、OpenSBIのPico-ITX用MMIO仲介許可表にない。
ドライバはリブート理由の初期化・設定でARSR、watchdogリセット制御でAPRRを使用する。
[watchdogドライバ](../linux-k3/drivers/watchdog/spacemit-k1-wdt.c) ·
[実機のPMP配置](../opensbi/lib/sbi/k3_pico_itx_pmp.h) ·
[現行のMMIO許可表](../opensbi/platform/generic/spacemit/k3_pico_itx_mmio.c)

修正 `223c5f2` で、Pico-ITXのLinux側ドメインからの32ビットMMIOを既存の許可表で仲介する。
書き込みは`APRR`（`0xd4051020`）のwatchdogリセットビット4と、`ARSR`（`0xd4051028`）の
ソフトウェア再起動理由ビット17〜14に限定する。
[MMIO許可表の変更](../opensbi/platform/generic/spacemit/k3_pico_itx_mmio.c)

クロスビルドしたELFで両レジスタの書き込みマスクを照合した。実機用FITを生成し、
OpenSBIの実行時範囲、出力のハッシュとUSB転送dry-runを確認した。watchdogドライバの
実行とMMIOの実機動作は未試験。
[実機用FITのビルド・照合記録](evidence/jupiter2-coexistence-16-pmp/qemu-pmp16.txt)

次は既存のImageで`spa_wdt_probe`を通過してLinuxがログインまで進むことを確認する。
[同梱FITの実機再試験](#ksb-099-retest)
