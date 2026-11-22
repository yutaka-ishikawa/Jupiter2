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

## K3 QEMUでのS-mode引き渡し試験

Linuxの代わりに小さなRV64ペイロードを使い、OpenSBIとKeystone SMの
初期化後に `untrusted-domain` のS-modeへ制御が渡ることを確認する。

```sh
riscv64-linux-gnu-gcc -nostdlib -static -no-pie -Wl,-Ttext=0x102200000 \
    -o entry.elf verifications/optee-coexistence/smode-handoff.S
riscv64-linux-gnu-objcopy -O binary -j .text entry.elf entry.bin
qemu-system-riscv64 -M jupiter2 \
    -cpu rva23s64,k3-pmacfg=true,pmp=true,num-pmp-regions=16,pmp-granularity=16 \
    -smp 16 -m 2G -display none -monitor none -serial stdio \
    -dtb boot.dtb -bios fw_dynamic.bin -kernel entry.bin \
    -device loader,file=tee.elf
```

`boot.dtb` は同居用DTB生成ツールの出力で、Linux側ドメインの開始アドレスを
固定しない構成を使う。UARTで `Boot HART Domain : untrusted-domain`、
`SM initialized`、`K3: S-mode handoff reached` を確認する。
ペイロードは出力後に待機する。QEMUを終了してログを保存する。
試験範囲はファームウェアからの初回引き渡しまで。

## K3 QEMUでのLinux引き渡し試験

カーネルからユーザー空間までの到達を確認するには、上記QEMUコマンドの
`-kernel entry.bin` を `-kernel Image` に変更し、
`-initrd initramfs.cpio -append 'console=ttyS0,115200 earlycon=sbi rdinit=/init'`
を加える。initramfsは以下のように作成できる。`gen_init_cpio` は
Linuxビルドディレクトリの `usr/gen_init_cpio` を使う。

```sh
riscv64-linux-gnu-gcc -static -O2 -Wall -Wextra -o linux-boot-init \
    verifications/optee-coexistence/linux-boot-init.c
cat > initramfs.list <<EOF_LIST
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
dir /proc 0555 0 0
dir /sys 0555 0 0
file /init ./linux-boot-init 0755 0 0
EOF_LIST
gen_init_cpio initramfs.list > initramfs.cpio
```

UARTの `K3 Linux userspace reached` とオンラインCPU数を記録する。
LinuxとKeystone SMの起動確認を対象とする。Enclaveの実行やOP-TEEへの
通信は同居ゲスト試験で確認する。
