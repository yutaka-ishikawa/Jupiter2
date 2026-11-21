# OP-TEE・Keystone同居ゲスト試験

同じLinuxプロセスから検証用TAを呼び、Keystoneの既存
[`hello-native`](../../samples/hello-native/) を16回create/run/destroyする。
各回のOCALL中にもTAを呼び、TA応答を検証してからEnclaveを再開する。
すべての検査が成功した場合、16回のEnclave実行と33回のTA呼出しを表示する。

## ビルド

現行Jupiter2のKeystone SDKとRV64向けOP-TEE TA dev kitを用意する。
`OPTEE_CLIENT_OUT` はRV64向けの `include/tee_client_api.h` と
`lib/libteec.so` を含むディレクトリ。

```sh
make -C verifications/optee-coexistence \
    CROSS_COMPILE=riscv64-linux-gnu- \
    SDK_DIR=/path/to/sdk-install \
    OPTEE_CLIENT_OUT=/path/to/optee-client/usr \
    TA_DEV_KIT_DIR=/path/to/optee-build/export-ta_rv64
```

`build/optee-coexistence` と
`build/ta/c25c295d-8af1-44f7-9f0e-657c39bc22ad.ta` を生成する。
TAはゲストのOP-TEEが信頼する評価用署名鍵でビルドする。

## K3 QEMUゲストでの実行

KeystoneとOP-TEEを起動した同居構成のゲストにテストバイナリを配置する。
`libteec` と `tee-supplicant` を配置してサービスを起動し、署名済みTAを
supplicantのTA検索先（例 `/lib/optee_armtz`）へ配置する。Keystoneの
`hello-native`、`eyrie-rt`、`loader.bin` は同じビルドの成果物を使う。
両ドライバーへアクセスできるユーザーでゲスト内から実行する。

```sh
./optee-coexistence ./hello-native ./eyrie-rt ./loader.bin
```

合格時の出力は `PASS: 16 enclave runs, 33 TA calls including OCALL`。
複数hart試験では、逐次試験の合格後、オンラインhartを選んで
`taskset -c` で別々のhartに割り当てた複数のプロセスを同時に実行し、
各プロセスの終了コードと出力を確認する。

この試験の範囲はTA呼出し、OCALLで中断したEnclaveの復帰、資源の解放。
PMPの隔離や遷移時の故障試験は
[同居設計の受入試験](../../doc/keystone-optee-coexistence-design.md#7-受入試験)で扱う。
