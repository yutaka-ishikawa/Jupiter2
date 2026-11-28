# Milk-V Jupiter2実機へのKeystone・OP-TEEスタック導入手順

SpacemiT K3搭載Milk-V Jupiter2 Pico-ITXで、開発PCで作成した成果物を実機へ転送し、
Linux・モジュール・アプリを配置して起動を確認する。まず使用中の起動設定をバックアップする。
OpenSBIの書き込みと復旧には専用の手順書を使う。
[実機の構成と適合性](../hardware/jupiter2/jupiter2-hardware-compatibility.md)

## 1. 導入範囲と順序

| 構成 | 使用する成果物 | 実機での起動 |
| --- | --- | --- |
| Keystoneのみ | 通常のNOR用bundle。USBで先に試験する場合はKeystone版の`FSBL.bin`と統合FITも用意 | RAM起動で確認し、永続導入する場合は使用中のOpenSBI区画を更新 |
| KeystoneとOP-TEEを同梱 | 同じビルドの`FSBL.bin`、Core入り統合FIT、Linux用DTB。Linux・ドライバ・アプリは対応する通常bundleを利用 | USB RAM起動で同梱FITを試験 |
| OP-TEEのみ | OP-TEE単独の`FSBL.bin`、統合FIT、Linux用DTBと対応TA | USB RAM起動。既存Linuxを使う場合はTEE・MPXY対応を確認 |

Linuxを更新する場合は、次の順序で進める。

1. 元のLinuxと起動設定を退避し、bundleから新Linuxを配置する。既存OpenSBIのまま、新Linuxと対応initrd・Linux用DTBで起動を確認する。この段階ではKeystoneドライバをロードしない。
2. 同じLinux Imageを使い、対象のOpenSBI／SMまたはOP-TEE入りFITで起動する。使用するファームウェアに対応するLinux用DTBを選び、構成に応じてKeystone・OP-TEEを試験する。

[配置とinitrdの生成](#6-新linuxとアプリを追加配置する) · [ブートイメージの導入](#8-ブートイメージの導入) · [Linuxからの動作確認](#9-実機での基本確認)

## 2. 書き込み前の停止条件

実機の型番、FWの版、FSBLがOpenSBIを読む媒体、使用中のLinuxのbootfsとrootfsを
UARTログと採取記録で照合する。NOR更新では実機の`opensbi`区画の容量と最終ITBを比較する。
販売元ファームウェア、元の起動設定、復旧経路を確認してから作業する。
[実機の採取記録](../hardware/jupiter2/README.md) · [起動媒体の特定とOpenSBI区画のバックアップ](milkv-jupiter2-opensbi-replacement.md#capture-opensbi-partition)

Pico-ITXの16枠同梱構成は、実機用FITとLinux用DTBの生成を開発PCで確認済み。
実機ではUARTでファームウェアとLinuxの到達段階を確認し、PMPや周辺機器の
検査は同梱構成の実機検査項目に従う。
[16枠同梱構成の検査項目](jupiter2-coexistence-16-pmp-plan.md#2-検証項目と合格条件)

## 3. 開発ホストで候補をビルドする

開発PCでの依存ツール導入、Linux・OpenSBIのビルド、NOR用bundleの作成は
実機用ビルド手順書に従う。通常bundleの成果物は`$OUT/bundle.tar.gz`と
`$OUT/bundle.tar.gz.sha256`。
[Linuxカーネルのビルド](jupiter2-build-install-test.md#linux-kernel-build) ·
[NOR導入用bundleの作成](jupiter2-build-install-test.md#nor-bundle)

USB RAM起動では、実機用ビルド手順書の第1章で構成に合うFSBLと統合FITを生成する。
OP-TEE入りの場合は第1.5節で同じFITに対応するLinux用DTBも作る。
[RAM起動用イメージの作成](jupiter2-build-install-test.md#ram-boot-images)

fTPMも使う場合は、署名済みTAとRV64版`tee-supplicant`を準備する。実機用Coreと
同じTA開発キットを使い、fTPMのクロスビルド手順の`OPTEE_OUT`には
`$PWD/.build-k3/optee-hardware/out`を指定する。
[fTPM TAのクロスビルド](jupiter2-ftpm-ta-test.md#ftpm-taのクロスビルド) ·
[tee-supplicantと試験プログラムのビルド](jupiter2-ftpm-ta-test.md#テストコードとtee-supplicantのビルド)

<a id="4-容量確認とインストールイメージ作成"></a>
## 4. bundleの転送と事前検査

開発PCで作成した`bundle.tar.gz`と`bundle.tar.gz.sha256`を実機へコピーする。
以下は実機の`$HOME/tmp`へコピーした例。展開済みの`bundle/`がある場合は、
別のディレクトリに転送し、`TRANSFER_DIR`をそのパスにする。

```bash
TRANSFER_DIR="$HOME/tmp"
(
    cd "$TRANSFER_DIR" || exit
    sha256sum -c bundle.tar.gz.sha256 || exit
    if [[ -e bundle || -L bundle ]]; then
        printf '展開先が既に存在します %s/bundle\n' "$PWD" >&2
        exit 1
    fi
    tar -xzf bundle.tar.gz
) && BUNDLE="$TRANSFER_DIR/bundle"
```

通常bundleでは、展開したディレクトリに`kernelrelease.txt`がある。
実機Linuxで読み取り専用の事前検査を実行する。

```bash
bash "${BUNDLE:?展開したbundleのパスを設定してください}/tools/preflight.sh"
```

このコマンドは同梱の`SHA256SUMS`を検証し、実機の`opensbi` NOR区画にFITが収まるか、
必要なコマンドがあるかを確認し、`/boot`・`/lib/modules`・`/opt`の空き容量を表示する。
使用中の起動媒体と`/boot`の対応は第5章で確認する。容量超過や照合エラーがあれば配置へ進まない。

実機側で使用するパッケージはBianbuなどの実機OS向けのものを入れる。
Python 3.11以上、Bash、coreutils、kmod、展開用のtarとgzipを使う。
Bianbuでinitrdを作る場合は`initramfs-tools`も用意する。NOR書き込み時の
`mtd-utils`の導入は書き込み手順を参照する。
[実機のNOR書き込み手順](milkv-jupiter2-opensbi-replacement.md#keystone配布用bundleからspi-norを更新する)

| 確認に使うファイル | 内容 |
| --- | --- |
| `kernelrelease.txt` | 同梱Imageとモジュールのリリース |
| `firmware/fw_dynamic.itb`、`capacity.json` | NOR用FITと作成時の容量検査 |
| `SHA256SUMS` | 展開後のファイルのハッシュ |
| `source-commit.txt`、`source-local.patch`、`source-untracked.txt` | 作成時のコミット、追跡済みファイルの差分、未追跡ファイルのパス |
| `tools/`、`docs/` | 実機用スクリプトと手順書 |

`--firmware-only`で作った配布物はFITの導入に使う。Linux配置にはImage・モジュール・
アプリを含む通常bundleを用意する。Linux用DTBは対象構成のものを別途配置する。
[FITのみを包装する手順](jupiter2-build-install-test.md#nor-firmware-only)

## 5. 実機の現状記録とバックアップ

導入前の採取手順に従って`INFO_DIR`を実機側で設定する。UARTは基板資料で電圧と
端子を確認し、115200/8N1・フロー制御なしで電源投入直後から記録する。
[実機情報の採取](../README.md#22-導入前の実機情報を採取) · [UART接続](milkv-jupiter2-uart.md)

`findmnt -T /boot`と採取記録を比較し、U-Bootが読むbootfsがマウントされていることを確認する。
元のImage、initrd、DTB、モジュールと起動設定を復旧用に残す。GRUBやextlinuxを使う場合は、
現在選んでいるエントリーと実際の設定ファイルを保存する。
NOR・GPT上のOpenSBI区画の記録とバックアップはブートイメージの手順で行う。
[OpenSBI区画のバックアップ](milkv-jupiter2-opensbi-replacement.md#capture-opensbi-partition)

### Linux起動設定の復旧用バックアップ

`env_k3.txt`を使う構成では、実機Linux上で`/boot/env_k3.txt.<日付>`を作り、
復旧用ディレクトリにもコピーする。`ROLLBACK`は復旧時に使用する。

```bash
ROLLBACK="${INFO_DIR:?採取先のINFO_DIRを設定してください}/jupiter2-rollback-$(date +%Y%m%d-%H%M%S)"
(
    set -eu
    mkdir -m 700 "$ROLLBACK"
    uname -r > "$ROLLBACK/original-kernel-release.txt"
    findmnt -T /boot > "$ROLLBACK/boot-mount.txt"
    lsblk -o NAME,PATH,FSTYPE,UUID,PARTUUID,PARTLABEL,MOUNTPOINTS > "$ROLLBACK/storage.txt"

    ENV_BACKUP="/boot/env_k3.txt.$(date +%Y%m%d-%H%M%S)"
    sudo test ! -e "$ENV_BACKUP"
    sudo test ! -L "$ENV_BACKUP"
    sudo cp -a -- /boot/env_k3.txt "$ENV_BACKUP"
    sudo cmp -- /boot/env_k3.txt "$ENV_BACKUP"
    sudo cp -a -- "$ENV_BACKUP" "$ROLLBACK/env_k3.txt"
    cd "$ROLLBACK"
    sudo sha256sum env_k3.txt > env_k3.txt.sha256
)
```

採取記録と復旧用ディレクトリのコピーを開発PCにも保存する。

## 6. 新Linuxとアプリを追加配置する

### 通常bundleを一括配置する

第5章のバックアップを済ませてから、実機Linuxで実行する。
`findmnt -T /boot`が示す対象を保存済みのbootfsと照合する。
初回試験では、旧Linuxのモジュールを残せる別リリースのImageとモジュールを使う。

```bash
BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
cat "$BUNDLE/kernelrelease.txt"
findmnt -T /boot
```

展開先とbootfsを確認してから、一括配置を実行する。

```bash
sudo bash "$BUNDLE/tools/install-linux.sh"
```

| bundle内のファイル | 実機の配置先 |
| --- | --- |
| `linux/Image` | `/boot/Image-<release>-keystone` |
| `linux/config` | `/boot/config-<release>-keystone` |
| `modules/<release>/`（Keystoneドライバを含む） | `/lib/modules/<release>/` |
| `apps/hello.ke`、`apps/hello-native.ke` | `/opt/keystone/<release>/` |

`<release>`は`kernelrelease.txt`の値。スクリプトは対象ごとに既存ファイルの
上書きとバックアップの保存を確認し、すべての回答を得てから配置する。
上書きの既定は拒否、バックアップの既定は保存。モジュールはリリース単位、
既存アプリ用ディレクトリのアプリはファイル単位で更新する。
旧版の退避先は各配置先の隣に`*.backup-*`として表示される。

配置と`depmod`の成功後、保存しないと選んだ退避ファイルを削除する。
途中で失敗した場合、スクリプトは配置済みの新ファイルの取り除きと旧ファイルの復元を試みる。
復元エラーが出た場合は表示された退避先を確認する。
一括配置後はinitrdとLinux用DTBを準備し、起動先の指定は第7章で行う。

### 新kernel用initrdを生成する

一括配置が成功したら、Bianbuの実機Linux上で新しいリリースのinitrdを作る。
`update-initramfs -k`に渡すのは`kernelrelease.txt`の値。
例えば`Image-6.18.3-keystone`に対応するリリースは`6.18.3`。

```bash
(
    set -eu
    BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
    KREL=$(cat "$BUNDLE/kernelrelease.txt")
    case "$KREL" in ''|.|..|*[!A-Za-z0-9._+-]*) exit 1;; esac
    cmp -- "$BUNDLE/linux/Image" "/boot/Image-$KREL-keystone"
    cmp -- "$BUNDLE/modules/$KREL/extra/keystone-driver.ko" \
      "/lib/modules/$KREL/extra/keystone-driver.ko"
    CONFIG="/boot/config-$KREL"
    if [[ -e "$CONFIG" || -L "$CONFIG" ]]; then
        cmp -- "$BUNDLE/linux/config" "$CONFIG"
    else
        sudo install -m 0644 -- "$BUNDLE/linux/config" "$CONFIG"
    fi

    INITRD="/boot/initrd.img-$KREL"
    INITRD_MODE=-c
    if [[ -e "$INITRD" ]]; then
        INITRD_MODE=-u
    fi
    if sudo update-initramfs "$INITRD_MODE" -k "$KREL"; then
        if [[ ! -s "$INITRD" ]]; then
            printf 'initrdの生成・更新に失敗しました。出力が存在しないか空です %s\n' "$INITRD" >&2
            exit 1
        fi
        printf 'initrdの生成・更新に成功しました（終了コード 0） %s\n' "$INITRD"
    else
        status=$?
        printf 'initrdの生成・更新に失敗しました（終了コード %s） %s\n' "$status" "$INITRD" >&2
        exit "$status"
    fi
)
```

`/boot/config-<release>`はinitramfs-toolsが参照する標準名。
内容が異なる場合は、bundleとインストール済みImage・モジュール・configの組を確認する。
生成成功後に、実機のrootfsに必要なストレージやファイルシステムのドライバが
Imageまたはinitrdに含まれることを確認する。

### Linux用DTBを配置する

Keystoneのみの試験では実機向けに準備した`k3-pico-itx-keystone.dtb`を使う。
既存OpenSBIで新Linuxを起動する第1段階でも、そのファームウェアに適合するDTBを選ぶ。
[Keystone用DTBの作成と配置](jupiter2-keystone-app-test.md#2-別名の試験用linux-dtbを作る開発pc)

OP-TEE入りのFITでは、同じFITビルドから生成したLinux用DTBを使う。
以下は第1.5節の`$OUT/release/images/k3-pico-itx-keystone-optee.dtb`を
実機の`$HOME/tmp`へ転送済みの場合の例。`DTB_DIR`は実機の起動に使うディレクトリに合わせる。
元の起動用DTBを保持できるよう、別名で配置する。
[OP-TEE入りFITとLinux用DTBの生成](jupiter2-build-install-test.md#optee-fit-build)

```bash
DTB_SRC="$HOME/tmp/k3-pico-itx-keystone-optee.dtb"
DTB_DIR=/boot/spacemit/6.18.3-generic
sudo install --backup=numbered -m 0644 -- "$DTB_SRC" "$DTB_DIR/"
```

一時起動時はU-Bootでこのファイルを明示して読み込み、`fdt print /firmware/optee`を確認する。
[同梱構成のU-Boot起動手順](jupiter2-ram-boot-guide.md#5-linuxを一時起動するuartでコマンドを直接入力)

### OP-TEEのLinux側ファイルを追加配置する

外部TAを試験する場合は、実機用Coreと同じTA開発キットで作成した署名済みTAと
RV64の`tee-supplicant`を実機へ転送する。通常のKeystone用bundleとは別に扱う。
既存のTAや`tee-supplicant`サービスの設定を保存し、実機のTA検索先と実行パスに合わせて配置する。

以下は既存サービスを使わず、fTPM用の成果物を`$HOME/jupiter2-optee/`へ転送した例。

```bash
OPTEE_STAGE="$HOME/jupiter2-optee"
FTPM_UUID=bc50d971-d4c9-42c4-82cb-343fb7f37896
sudo install -D --backup=numbered -m 0644 \
  "$OPTEE_STAGE/$FTPM_UUID.ta" "/lib/optee_armtz/$FTPM_UUID.ta"
sudo install -D --backup=numbered -m 0755 \
  "$OPTEE_STAGE/tee-supplicant" /usr/local/sbin/jupiter2-tee-supplicant
```

OP-TEE入りFITで起動してから、実機OSの既存サービスか、別端末で
`sudo /usr/local/sbin/jupiter2-tee-supplicant`を使う。
[OP-TEEとTAの動作確認](#op-teeの試験)

<a id="install-kernel-modules-only"></a>
### カーネルモジュールのみをインストールする

実機Linuxで実行する。展開先が `$HOME/tmp/bundle` と異なる場合は、
実際のパスを `BUNDLE` に設定する。モジュール一式の新規配置と
Keystoneドライバ単体の追加・更新のうち、該当する方を実行する。
`findmnt -T /boot`を第5章の記録と照合し、対象のbootfsを使う。

#### モジュール一式の新規配置・更新

bundleと同一ビルドのLinux Imageに対応する
モジュール一式を新規配置する。確認に失敗した場合は後続の配置へ進まない。
既存の `/lib/modules/<release>/` があれば上書きするか確認する。
上書きを承認した場合は、旧ディレクトリをバックアップとして残すか確認する。
既定は保存。保存しない場合も、入れ替えとinitrdの生成・更新が成功するまでは旧一式を一時退避する。
対象のImageと同じビルドのモジュールを使う。
[新kernel用initrdの生成手順](#新kernel用initrdを生成する)を参照し、
対象の `/boot` をマウントして、同じビルドの `/boot/config-<release>` を用意する。
スクリプトは `depmod` に続けてinitrdを生成・更新する。交換前のモジュールが既存initrdに残るため、
スクリプトが成功してから、U-Bootで新しい `initrd.img-<release>` を使って起動する。

```bash
(
    set -eu
    BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
    KREL=$(cat "$BUNDLE/kernelrelease.txt")
    case "$KREL" in ''|.|..|*[!A-Za-z0-9._+-]*) exit 1;; esac
    cmp -- "$BUNDLE/linux/Image" "/boot/Image-$KREL-keystone" || {
        status=$?
        printf 'エラー: bundleと起動用Imageの照合に失敗しました（cmp終了コード %s）。\n' "$status" >&2
        printf '起動用Imageと同じビルドのbundleを指定してください。モジュール交換とinitrd更新を中止します。\n' >&2
        exit "$status"
    }
    bash "$BUNDLE/tools/verify.sh"
    SRC="$BUNDLE/modules/$KREL"
    DEST="/lib/modules/$KREL"
    test -d "$SRC"
    test -s "/boot/config-$KREL"
    command -v update-initramfs >/dev/null
    BACKUP=
    KEEP_BACKUP=yes
    if [[ -e "$DEST" || -L "$DEST" ]]; then
        read -r -p "$DEST を上書きしますか？ [y/N] " answer || exit 1
        case "$answer" in y|Y) ;; *) exit 1;; esac
        read -r -p '旧モジュールのバックアップを残しますか？ [Y/n] ' answer || exit 1
        case "$answer" in
            ''|y|Y) ;;
            n|N) KEEP_BACKUP=no ;;
            *) exit 1 ;;
        esac
        BACKUP="$DEST.backup-$(date +%Y%m%d-%H%M%S)"
        test ! -e "$BACKUP"
        test ! -L "$BACKUP"
    fi

    STAGE=$(sudo mktemp -d "/lib/modules/.$KREL.install.XXXXXX")
    sudo cp -a -- "$SRC" "$STAGE/modules"
    if [[ -n "$BACKUP" ]]; then
        sudo mv -T -- "$DEST" "$BACKUP"
        printf '旧モジュールの退避先 %s\n' "$BACKUP"
    fi
    if ! sudo mv -T -- "$STAGE/modules" "$DEST"; then
        if [[ -n "$BACKUP" ]]; then
            sudo mv -T -- "$BACKUP" "$DEST"
        fi
        exit 1
    fi
    sudo rmdir -- "$STAGE"
    sudo depmod -a "$KREL"
    INITRD="/boot/initrd.img-$KREL"
    if [[ -e "$INITRD" ]]; then
        INITRD_MODE=-u
    else
        INITRD_MODE=-c
    fi
    if sudo update-initramfs "$INITRD_MODE" -k "$KREL"; then
        if [[ ! -s "$INITRD" ]]; then
            printf 'initrdの生成・更新に失敗しました。出力が存在しないか空です: %s\n' "$INITRD" >&2
            exit 1
        fi
        printf 'initrdの生成・更新に成功しました（終了コード 0）: %s\n' "$INITRD"
    else
        status=$?
        printf 'initrdの生成・更新に失敗しました（終了コード %s）: %s\n' "$status" "$INITRD" >&2
        exit "$status"
    fi
    if [[ -n "$BACKUP" && "$KEEP_BACKUP" == no ]]; then
        sudo rm -rf -- "$BACKUP"
        printf '一時退避した旧モジュールを削除しました: %s\n' "$BACKUP"
    fi
)
```

#### Keystoneドライバ単体の追加・更新

起動中のImageが
bundleの `linux/Image` と同じビルドであることをU-Bootの起動記録とImageの照合で
確認してから実行する。以下は `/boot/Image-<release>-keystone` を起動した場合の例。
更新前に実行中のEnclaveとKeystoneアプリを終了する。ロード済みの場合はドライバを
取り外してから更新する。旧ファイルは `keystone-driver.ko.~1~` などの連番付きで保存する。
対象releaseのinitrdと標準名のconfigを用意し、`depmod`の後でinitrdを更新する。
初めてinitrdを作る場合は前掲の生成手順を使う。
Imageも変更した場合は、対応する新Imageとモジュール一式を別リリースとして配置する。

```bash
(
    set -eu
    BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
    bash "$BUNDLE/tools/verify.sh"
    KREL=$(cat "$BUNDLE/kernelrelease.txt")
    case "$KREL" in ''|.|..|*[!A-Za-z0-9._+-]*) exit 1;; esac
    test "$(uname -r)" = "$KREL"
    cmp "$BUNDLE/linux/Image" "/boot/Image-$KREL-keystone"
    test -d "/lib/modules/$KREL"
    cmp -- "$BUNDLE/linux/config" "/boot/config-$KREL"
    INITRD="/boot/initrd.img-$KREL"
    test -s "$INITRD"
    command -v update-initramfs >/dev/null
    SRC="$BUNDLE/modules/$KREL/extra/keystone-driver.ko"
    DEST="/lib/modules/$KREL/extra/keystone-driver.ko"
    test -s "$SRC"
    test ! -L "$DEST"
    if [[ -e "$DEST" ]]; then
        test -f "$DEST"
    fi
    if [[ -d /sys/module/keystone_driver ]]; then
        sudo modprobe -r keystone_driver
    fi
    sudo install -D --backup=numbered -m 0644 -- "$SRC" "$DEST"
    sudo depmod -a "$KREL"
    if sudo update-initramfs -u -k "$KREL"; then
        if [[ ! -s "$INITRD" ]]; then
            printf 'initrdの更新に失敗しました。出力が存在しないか空です %s\n' "$INITRD" >&2
            exit 1
        fi
        printf 'initrdの更新に成功しました（終了コード 0） %s\n' "$INITRD"
    else
        status=$?
        printf 'initrdの更新に失敗しました（終了コード %s） %s\n' "$status" "$INITRD" >&2
        exit "$status"
    fi
    sudo modprobe keystone_driver
    test -c /dev/keystone_enclave
)
```

initrdの更新に失敗した場合は、表示された終了コードと旧ドライバの退避先を確認する。
対象releaseのinitrdを正しく更新してから次回の起動に使う。

### tools・appsを個別に配置する

実機Linuxで、転送・展開済みの通常bundleを使う。パスを実際の展開先に置き換え、
以降は必要な項目を実行する。

**appsのみ**。`hello.ke` と `hello-native.ke` をリリース別に置く。実行は対応する
Linux・Keystoneドライバ・SMで起動した後に行う。同じリリースへ再配置する場合は、
旧アプリを連番付きで保存してから更新する。

```bash
(
    set -eu
    BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
    bash "$BUNDLE/tools/verify.sh"
    KREL=$(cat "$BUNDLE/kernelrelease.txt")
    case "$KREL" in ''|.|..|*[!A-Za-z0-9._+-]*) exit 1;; esac
    DEST="/opt/keystone/$KREL"
    test -s "$BUNDLE/apps/hello.ke"
    test -s "$BUNDLE/apps/hello-native.ke"
    test ! -L "$DEST"
    sudo install -d -- "$DEST"
    sudo install --backup=numbered -m 0755 -- \
      "$BUNDLE/apps/hello.ke" "$BUNDLE/apps/hello-native.ke" "$DEST/"
)
```

**toolsのみ**。`check-capacity.py` は単体で配置できる。実機で実行すると
OpenSBI用NOR区画の容量を読み取る。

```bash
(
    set -eu
    BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
    bash "$BUNDLE/tools/verify.sh"
    sudo install -m 0755 -- "$BUNDLE/tools/check-capacity.py" /usr/local/bin/jupiter2-check-capacity
    python3 /usr/local/bin/jupiter2-check-capacity --json
)
```

`verify.sh`、`preflight.sh`、`install-linux.sh`、`run-hello.sh` は
自身の親ディレクトリをbundleとして扱う。これらのツールだけを利用する場合は、
展開済みbundleをそのまま保持し、実機のシステム領域にLinuxファイルやアプリを
配置せずに必要なツールを呼び出す。例えば整合性の再確認は
`bash "$BUNDLE/tools/verify.sh"` で行う。

### 実機Linux上でKeystoneとOP-TEEをテストする

第7〜8章の起動手順を済ませ、試験対象のファームウェアと対応するImage・initrd・DTBで
実機Linuxを起動してから実行する。

#### Keystoneの試験

Keystone SMで起動した実機Linuxで実行する。スクリプトは起動中のリリースと
配置済みドライバをbundleと照合し、ドライバを読み込んで`hello.ke`と`hello-native.ke`を順に実行する。

```bash
BUNDLE="${BUNDLE:-$HOME/tmp/bundle}"
sudo bash "$BUNDLE/tools/run-hello.sh"
```

両サンプルの正常終了と、試験後もLinuxが応答することを確認する。
混成CPUでの試験はLinux CPU番号とhart IDの対応を確認してからX100・A100で実施する。
[Keystoneアプリの詳しい試験](jupiter2-keystone-app-test.md#6-ドライバーとhello二種を試験する実機linux)

#### OP-TEEの試験

Linuxのビルド設定で `CONFIG_TEE`、`CONFIG_OPTEE`、`CONFIG_RISCV_SBI_MPXY_MBOX` を確認する。
実機LinuxではMPXYに対応するLinux用DTBのノード、OP-TEEドライバの初期化ログ、
TEEデバイスを確認する。

```bash
test -d /sys/firmware/devicetree/base/firmware/optee
sudo dmesg | grep -Ei 'op.?tee|mpxy'
ls -l /dev/tee[0-9]* /dev/teepriv[0-9]*
```

`optee: initialized driver` と、通常は `/dev/tee0`・`/dev/teepriv0` が見えることを確認する。
デバイス番号は構成により変わる。ドライバ初期化を確認したら、TAの呼び出しを試す。
[Pico-ITXで確認した起動結果](jupiter2-coexistence-16-pmp-plan.md#pico-itx-linux-pass)

<a id="pico-itx-optee-ta-smoke"></a>
##### 現在のFITで内蔵のdevice.ptaを確認する

今回のPico-ITXでは、Linuxドライバが `device.pta` のセッションを開いて閉じるところまでUARTで確認した。
同じ起動の実機Linuxで、デバイス列挙の結果を確認する。K3実機用Coreの既定では、RTC PTAのUUID
`f389f8c8-845f-496c-8bbe-d64bd24c92fd` を持つ `optee-ta-…` が見える。
[実機UART](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-boot-pass-uart.txt) ·
[LinuxのOP-TEEデバイス列挙](../linux-k3/drivers/tee/optee/device.c)

```bash
ls -l /dev/tee[0-9]* /dev/teepriv[0-9]*
ls -l /sys/bus/tee/devices/
```

ユーザー空間からも呼び出す場合は、**開発PC**のJupiter2リポジトリのルートで次のコマンドを実行する。
Linux用のRV64クライアントを作り、Coreに組み込まれた `device.pta` に読み取り専用の
`PTA_CMD_GET_DEVICES` を送る。FIT・Linux・DTBはそのまま使える。`tee-supplicant` や
署名済み外部TAの配置は不要。
[device.ptaのソース](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59/core/pta/device.c)

```bash
(
    set -eu
    CROSS="${CROSS_COMPILE:-riscv64-linux-gnu-}"
    OPTEE_SRC="${OPTEE_SRC:-$PWD/.build-k3/optee-hardware/optee_os}"
    TEST_OUT="$PWD/.build-k3/optee-hardware/pta-smoke"
    CLIENT="$TEST_OUT/optee_client"
    CLIENT_REV=9f4414f62dfc5692fd39f760515ce2d344d07b6d

    test -s "$OPTEE_SRC/lib/libutee/include/pta_device.h"
    mkdir -p "$TEST_OUT"
    if [[ ! -e "$CLIENT" ]]; then
        git clone https://github.com/OP-TEE/optee_client.git "$CLIENT"
        git -C "$CLIENT" checkout --detach "$CLIENT_REV"
    fi
    test "$(git -C "$CLIENT" rev-parse HEAD)" = "$CLIENT_REV"
    make -C "$CLIENT" O="$TEST_OUT/client" CROSS_COMPILE="$CROSS" build-libteec

    cat > "$TEST_OUT/device-pta-smoke.c" <<'EOF'
#include <stdio.h>
#include <pta_device.h>
#include <tee_client_api.h>

int main(void)
{
    const TEEC_UUID uuid = PTA_DEVICE_UUID;
    unsigned char devices[1024];
    TEEC_Context context;
    TEEC_Session session;
    TEEC_Operation operation = { 0 };
    uint32_t origin = 0;
    TEEC_Result rc;
    size_t bytes;

    rc = TEEC_InitializeContext("optee-tz", &context);
    if (rc != TEEC_SUCCESS) {
	fprintf(stderr, "TEEC_InitializeContext: %#x\n", rc);
	return 1;
    }

    rc = TEEC_OpenSession(&context, &session, &uuid, TEEC_LOGIN_PUBLIC,
                          NULL, NULL, &origin);
    if (rc != TEEC_SUCCESS) {
	fprintf(stderr, "TEEC_OpenSession: %#x origin=%u\n", rc, origin);
	TEEC_FinalizeContext(&context);
	return 1;
    }

    operation.paramTypes = TEEC_PARAM_TYPES(TEEC_MEMREF_TEMP_OUTPUT, TEEC_NONE,
                                            TEEC_NONE, TEEC_NONE);
    operation.params[0].tmpref.buffer = devices;
    operation.params[0].tmpref.size = sizeof(devices);
    rc = TEEC_InvokeCommand(&session, PTA_CMD_GET_DEVICES, &operation, &origin);
    bytes = operation.params[0].tmpref.size;
    TEEC_CloseSession(&session);
    TEEC_FinalizeContext(&context);

    if (rc != TEEC_SUCCESS || !bytes || bytes > sizeof(devices) ||
        bytes % sizeof(TEEC_UUID)) {
	fprintf(stderr, "PTA_CMD_GET_DEVICES: %#x origin=%u bytes=%zu\n",
		rc, origin, bytes);
	return 1;
    }

    printf("PASS OP-TEE device.pta: %zu device(s)\n", bytes / sizeof(TEEC_UUID));
    return 0;
}
EOF

    "${CROSS}gcc" -static -O2 -Wall -Wextra -Werror \
        -I"$CLIENT/libteec/include" -I"$OPTEE_SRC/lib/libutee/include" \
        "$TEST_OUT/device-pta-smoke.c" "$TEST_OUT/client/libteec/libteec.a" \
        -pthread -o "$TEST_OUT/device-pta-smoke"
)
```

`.build-k3/optee-hardware/pta-smoke/device-pta-smoke` を **Jupiter2実機**の `$HOME` に転送して実行する。
`PASS OP-TEE device.pta: … device(s)` と終了コード0で、ユーザー空間からOP-TEE Coreへセッションを
開き、コマンドに対して1件以上のデバイス情報が返ることを確認できる。

```bash
sudo "$HOME/device-pta-smoke"
printf 'OP-TEE PTA exit=%s\n' "$?"
```

エラー時はクライアントが表示するAPI名・戻り値・`origin` と、
`sudo dmesg | grep -Ei 'op.?tee|mpxy'` の結果、OP-TEEのUARTを採取する。

##### 外部TAとfTPM TAを確認する

今回の実機では、OP-TEEがeFuseバンク1・2の未書き込みを検出し、HUKの導出を拒否した。
このSpacemiT版の `CFG_REE_FS_TA=y` では、外部TAのロード時にもCoreが
バージョン情報の管理にセキュアストレージを使う。fTPMを含む外部TAの実機試験はHUKが使える環境で行う。
[実機のHUKログ](evidence/jupiter2-coexistence-16-pmp/2026-11-28-pico-itx-linux-boot-pass-uart.txt) ·
[K3のHUK実装](https://github.com/spacemit-com/optee_os/blob/2fbd6ae54d89ff8621cdc1b5379c6bbe6f2d3c59/core/arch/riscv/plat-k3/k3_huk.c#L88-L103)

REE側のファイルからfTPM TAをロードする試験では、Linux用DTBに有効な `microsoft,ftpm` ノードを
用意する。実機同梱用のDTB生成処理はMPXYと `/firmware/optee` を追加する。参照DTBに
`microsoft,ftpm` がなければ、LinuxがfTPMドライバをバインドするためのノードは別途必要。
[LinuxのfTPMドライバ](../linux-k3/drivers/char/tpm/tpm_ftpm_tee.c) ·
[REEに配置したfTPM TAの試験](jupiter2-ftpm-ta-test.md#linuxのtpmリソースマネージャー経由の試験)

fTPMのLinuxドライバをモジュールとして用意した構成では、fTPM TAを前述の手順で配置し、
`tee-supplicant` を起動してから `sudo modprobe tpm_ftpm_tee` を実行する。

`tpm2-tools`を実機に用意し、sysfsとログでfTPMに対応するTPMデバイスを特定する。
以下の`TPM_DEVICE`は、実機で割り当てられた番号に合わせる。

```bash
sudo dmesg | grep -Ei 'op.?tee|ftpm|tpm'
ls -l /dev/tpmrm*
TPM_DEVICE=/dev/tpmrm0
sudo tpm2_getrandom -T "device:$TPM_DEVICE" --hex 16
```

終了コード0で16バイトに相当する32桁の16進数が返れば、fTPM TAの応答を確認できた。
外部TAを直接確認する場合は、同じCore向けに作成した`ftpm-smoke`を実機へ転送して
`sudo ./ftpm-smoke`を実行し、`fTPM PASS`と終了コード0を確認する。
[TA直接呼び出しの準備](jupiter2-ftpm-ta-test.md#テストコードとtee-supplicantのビルド) ·
[TPMデバイスを使う試験](jupiter2-ftpm-ta-test.md#linuxのtpmリソースマネージャー経由の試験)

<a id="pico-itx-ima-ftpm"></a>
##### Linux IMAとfTPMのPCR 10を確認する

2026年11月28日のPico-ITX実機で `CONFIG_TCG_TPM=y`、`CONFIG_TCG_FTPM_TEE=m`、
`CONFIG_SECURITYFS=y`、`# CONFIG_INTEGRITY is not set` を確認した。`securityfs` は
`/sys/kernel/security` にマウント済みで、`ima/ascii_runtime_measurements`、`/sys/class/tpm/tpmN`、
`/dev/tpmrmN` はなかった。IMAはカーネルで無効で、TPMも未登録だった。

IMAを有効にしたImage、同じビルドのモジュール、対応するinitrdでLinuxを一時起動する。
Keystone入りの構成では、カーネルに対応するKeystoneドライバも配置する。
ログイン後に測定ログの `boot_aggregate` と、fTPMを試験する場合はTPMデバイスを確認する。
[Linuxカーネルのビルド](jupiter2-build-install-test.md#linux-kernel-build) ·
[カーネルとモジュールの配置](#6-新linuxとアプリを追加配置する) ·
[USB RAM起動手順](jupiter2-ram-boot-guide.md#coexistence-linux-boot)

```bash
sudo head -n 5 /sys/kernel/security/ima/ascii_runtime_measurements
ls -ld /sys/class/tpm/tpm[0-9]* /dev/tpmrm[0-9]*
```

fTPMに測定を反映するには、`ima_init()` が走る前にfTPMを登録する。ログイン後に
`modprobe` でTPMデバイスが現れても、その起動のIMAが初期化時に `TPM-bypass` だった場合は
PCR 10を更新しない。QEMUでは早期登録した場合にだけPCR 10が更新された。
実機ではHUKを使える状態とfTPMの早期登録経路を用意し、IMAログに追加された測定に対応する
SHA-256バンクのPCR 10更新を `tpm2_pcrread -T device:/dev/tpmrmN sha256:10` で照合する。
`N` はfTPMに割り当てられた番号。
[カーネルのIMA初期化](../linux-k3/security/integrity/ima/ima_init.c#L118) ·
[QEMUでの早期・遅延登録の比較](evidence/jupiter2-ftpm-ima/uart.txt)

同梱構成では、同じ起動中にKeystoneとOP-TEEの結果を採取する。
同時実行、再起動後の保持、IMA、PMPなどの追加確認は構成に合う実機検査項目を使用する。
[同梱構成の実機検査](jupiter2-coexistence-16-pmp-plan.md#2-検証項目と合格条件)

## 7. 試験用boot entryを追加する

第1段階では既存OpenSBIで、配置したLinuxと対応するinitrd・Linux用DTBを一時起動する。
第5章の記録で特定した起動経路を使う。

### U-Bootから直接起動する場合

Bianbuの`env_k3.txt`を使う構成では、UARTでU-Bootを止め、試験用のImage、initrd、
DTBをその起動のRAM上で指定する。起動試験の前に`/boot/env_k3.txt`を編集せず、
`saveenv`も実行しない。旧ファイルとそのバックアップは保持する。

| 指定する項目 | U-Bootでの指定例 | 事前に照合する実機上のファイル |
| --- | --- | --- |
| `knl_name` | `Image-6.18.3-keystone` | `/boot/Image-6.18.3-keystone` |
| `ramdisk_name` | `initrd.img-6.18.3` | `/boot/initrd.img-6.18.3` |
| `dtb_dir`と`fdtfile` | `spacemit/6.18.3-generic`と`k3-pico-itx-keystone.dtb` | `/boot/`以下に配置した実際のディレクトリとLinux用DTB |

Imageとinitrdのリリースは`kernelrelease.txt`、DTBのパスは第6章の配置結果に合わせる。
bootfsのデバイス番号とrootfsのPARTUUIDは採取記録およびU-Bootの一覧で確認する。
U-Bootのプロンプトでは、RAM起動ガイドの第4〜5節に従いUFSとファイルを確認し、
Image・initrd・DTBを読み込んで`booti`で起動する。各`load`が成功してから次へ進む。
[UFSと起動ファイルの確認](jupiter2-ram-boot-guide.md#4-ufsと起動ファイルを確認するuart) ·
[U-Bootでの一時起動](jupiter2-ram-boot-guide.md#5-linuxを一時起動するuartでコマンドを直接入力)

#### 正常起動後にenv_k3.txtへ永続化する

新Linuxを通常起動でも使用する場合は、第1段階の合格条件を確認してから保存する。
Bianbuの標準U-Boot構成では、試験に成功した`knl_name`、`ramdisk_name`、`dtb_dir`を
`/boot/env_k3.txt`の既存行に反映する。使用するLinux用DTBが通常起動で
選ばれる設定かどうかも確認する。機種情報で自動選択する設定では、その設定で
読まれるDTB名を起動ログで確認する。

設定を保存して`sync`し、UARTで変数を指定せずに通常再起動して同じLinuxが選ばれることを確認する。
失敗時は第10章の元の起動設定への復旧を行う。
[K3の起動と設定の資料](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md)

### EDK2からGRUBを使っている場合

動作中entryを複製し、次だけ変更した「Keystone trial」を追加する。

- kernelを`Image-KERNELRELEASE-keystone`へ変更。
- initramfsを新releaseの`initrd.img-KERNELRELEASE`へ変更。
- root UUID、console、storage関連引数、必要なDT指定は実機の正常entryを引き継ぐ。

GRUBが参照するパスは、`/boot`が別partitionかrootfs内かで異なる。
既存entryと`grub-probe`等で確認し、Linux上のパスを無条件に転記しない。
`/etc/grub.d/40_custom`等のOS標準の追加方法を使い、`update-grub`後に生成されたentryを点検する。
直接`grub.cfg`を書き換えて永続設定としない。
署名強制がある環境では、新Imageとmoduleに認可された署名が必要。強制無効化を前提にしない。

### extlinux等を使っている場合

実際に使用されている設定へ別LABELを追加し、同様に新Image/initramfsと必要なDTを指定する。
EDK2が使わない`extlinux.conf`を編集しても反映されない。loaderが特定できない場合は
ファイル配置までで止め、使用中entryの形式を確定する。

GRUB/extlinuxで別entryを追加する場合は、既定entryを旧環境のまま残し、UART/画面から手動でtrialを選ぶ。
`init=/bin/bash`、`root=/dev/vda`、QEMUのvirtio/9p設定は持ち込まない。
最初は通常メモリー量のhelloだけを試し、256 MiB EPM用CMAは後段で
[大容量EPM手順](keystone-large-epm.md)に従い実機の予約領域と照合して追加する。

### 第1段階の合格条件

既存OpenSBIで新Linuxが起動し、`uname -r`がbundleの`kernelrelease.txt`と一致することを確認する。
今回のPico-ITX例では全16 CPU、ストレージ、ネットワーク、UART、通常のタイマー動作を確認する。
この段階のログを保存してから、第8章の新ファームウェアの確認へ進む。

## 8. ブートイメージの導入

**USB RAM起動**。構成に合う`FSBL.bin`と統合FITを開発PCから転送する。
同じLinux Imageとinitrdを使い、使用するファームウェアに対応するLinux用DTBを選ぶ。
OP-TEE入りのFITは第6章で配置した同じビルドのLinux用DTBを選び、
U-Bootで`/firmware/optee`を確認してから起動する。
[USB RAM起動手順](jupiter2-ram-boot-guide.md)

**KeystoneのNOR永続導入**。第1段階とRAM起動の確認を済ませ、対象のOpenSBI区画と
元のイメージのバックアップを確認する。実機への書き込み、読み戻し、再起動は
ブートイメージの専用手順に従う。
[通常bundleのNOR書き込み](milkv-jupiter2-opensbi-replacement.md#keystone配布用bundleからspi-norを更新する) ·
[元のOpenSBIへ復旧](milkv-jupiter2-opensbi-replacement.md#restore-stack-opensbi)

## 9. 実機での基本確認

試験対象のファームウェアと対応するImage、initrd、Linux用DTBで実機Linuxが起動したら、
UARTログにCoreやSMなど選んだファームウェアの初期化が記録されていることを確認する。
次に、Linuxのリリース、全CPUの起動、rootfsと起動引数を確認する。

```bash
uname -r
cat /sys/devices/system/cpu/online
cat /proc/cmdline
findmnt /
```

構成に該当する試験を実行し、使用したImageとDTB、UARTログと結果を保存する。
[KeystoneとOP-TEEの試験コマンド](#実機linux上でkeystoneとop-teeをテストする)

## 10. 復旧と正式採用

### 第1段階のrollback

起動設定を保存する前の失敗は、元の設定で再起動して復帰する。
配置やinitrdの作成中に失敗した場合はエラーと配置先を確認し、旧Linuxの起動設定を使う。

`env_k3.txt`へ永続化した後は、第5章の復旧ディレクトリから元の設定を復元する。
現在のLinuxで操作できなければ、UARTで旧kernel・旧initrd・旧DTBを指定して一時起動する。
販売元Linuxの一時起動手順を使うときは、保存した`env_k3.txt.<日付>`を読み込むパスに指定する。
[販売元Linuxの一時起動](jupiter2-vendor-linux-ram-boot.md#販売元の設定を取り込む)

復旧ディレクトリの実際のパスを`ROLLBACK`に設定してから実行する。

```bash
(
    set -eu
    cd "${ROLLBACK:?復旧ディレクトリを設定してください}"
    read -r ENV_HASH _ < env_k3.txt.sha256
    printf '%s  env_k3.txt\n' "$ENV_HASH" | sudo sha256sum -c -
    sudo cp -a -- env_k3.txt /boot/env_k3.txt
    sudo cmp -- env_k3.txt /boot/env_k3.txt
    sync
)
```

次の再起動で`uname -r`が`original-kernel-release.txt`の値へ戻ることを確認する。
GRUB・extlinux方式では保存した設定と元のエントリーを使う。GRUBの設定を戻した後は
`update-grub`で再生成する。

旧kernelを一時起動できない場合は、実機のストレージへアクセスできる復旧用Linuxを使う。
第5章の採取結果でbootfsのPARTUUIDを確認し、対象パーティションをマウントして
元の`env_k3.txt`を戻す。復旧用Linuxではマウント先の直下に配置する。

```bash
(
    set -eu
    cd "${ROLLBACK:?復旧ディレクトリを設定してください}"
    read -r ENV_HASH _ < env_k3.txt.sha256
    printf '%s  env_k3.txt\n' "$ENV_HASH" | sudo sha256sum -c -
    sudo mkdir -p /mnt/jupiter2-bootfs
    sudo mount "${BOOTFS_DEV:?実機のbootfsデバイスを設定してください}" /mnt/jupiter2-bootfs
    sudo cp -a -- env_k3.txt /mnt/jupiter2-bootfs/env_k3.txt
    sudo cmp -- env_k3.txt /mnt/jupiter2-bootfs/env_k3.txt
    sync
    sudo umount /mnt/jupiter2-bootfs
)
```

旧Linuxが起動してから、退避した旧ファイルと今回の配置先を照合し、不要な試験用ファイルを個別に整理する。

### OpenSBIを復旧する場合

NORを更新した後に問題が起きた場合は、元のOpenSBIを専用手順で復旧する。
Linux起動設定も変更した場合は、必要に応じて上のrollbackを実施する。
[ブートイメージの復旧](milkv-jupiter2-opensbi-replacement.md#restore-stack-opensbi)

### 正式採用

新Linux、対象ファームウェア、Keystone・OP-TEEの試験結果を区別して保存する。
使用したコミット、Image・DTB・FITのハッシュ、起動ログ、試験結果と復旧用ファイルを
導入記録にまとめる。

## 関連資料

- [実機情報とfirmware適合性](../hardware/jupiter2/jupiter2-hardware-compatibility.md)
- [EDK2を維持したOpenSBI置換・復旧](milkv-jupiter2-opensbi-replacement.md)
- [buildとinstallの分離](make-build-install.md)
- [SPI NOR読取り調査](jupiter2-spi-nor-inspection.md)
- [SstcとSM timerの共存](keystone-sstc-coexistence.md)
- [Keystone移植計画](keystone-porting-plan.md)
- [既知不具合台帳](keystone-bug-report.md)
- [KeystoneとOP-TEEの同居設計](keystone-optee-coexistence-design.md)
