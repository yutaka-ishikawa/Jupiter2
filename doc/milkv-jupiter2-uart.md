# Milk-V Jupiter2のUART接続とPC側コンソール操作

更新日：2026-11-20（JST）。対象はSpacemiT K3搭載Milk-V Jupiter2 SBC。
新kernelの試験前に、PCから起動ログを読めることと、キー入力でU-Bootを停止できることを確認する。
Jupiter（K1/M1）、Jupiter2 NX、Dev Kitの端子配置とは区別する。

## 1. 接続に使うもの

- PCと、そのOSに対応するシリアル端末ソフト。
- 基板のUART信号電圧に適合するUSB–TTL UART変換アダプター。
- TX/RX/GNDを接続できるケーブル。
- Jupiter2本体用の通常電源。

**UARTは基板上のデバッグ端子へ接続する。書込み用DRD Type-C端子にUSBケーブルを挿す操作とは別。**
USB–RS-232変換器をTTL UARTへ直接接続しない。
USBアダプターの電源出力が3.3 Vでも、TX信号が同じ電圧とは限らないため、仕様を確認する。

Milk-V公式の[Quick Start](https://milkv.io/docs/jupiter2/getting-started/quick-start)が参照する
[K3 Pico-ITX User Guide](https://cdn-resource.spacemit.com/file/product/K3/k3_pico_ug_en.pdf)の
第3.2節と第5.2節にUART接続がある。
端子位置は第2.1節の基板図の「16 UART pin header」。
これは図中の位置番号であり、UARTコネクターのpin番号ではない。

## 2. 配線する

Jupiter2を正常shutdownして電源を外し、USB–UARTアダプターもPCから外した状態で配線する。
[公式ガイドの接続写真](https://docs.bit-brick.com/assets/images/signal00-e593ea4700d0665370045c021d141f49.png)
と手元の基板を照合する。写真には基板側のTX・RX・GNDが示されている。

| Jupiter2のデバッグUART | USB–UARTアダプター側 |
| --- | --- |
| TX（基板から送信） | RX／RXD（PC側で受信） |
| RX（基板で受信） | TX／TXD（PC側から送信） |
| GND | GND |

TXとRXは交差接続し、GNDは共通にする。
**アダプターのVCC／5V／3V3電源線は接続しない。本体は通常の電源から給電する。**
ケーブルの線色は製品ごとに異なるため、色ではなく信号名で確認する。

端子の左右は基板を見る向きで変わる。写真と違う基板revisionでは、そのrevisionの資料で確認する。
公開ガイドのUART説明では信号電圧の数値を確認できなかったため、本書では一律3.3 V等とは断定しない。
接続前に対象基板の回路図・メーカー情報とアダプターの仕様で電圧を合わせる。
FPC上の別UARTやEC用UARTへ接続しない。

## 3. PC側ソフトと通信設定

| 項目 | 設定 |
| --- | --- |
| 通信速度 | 115200 bps |
| データ長 | 8 bit |
| パリティ | なし |
| ストップビット | 1 bit |
| ハードウェアフロー制御（RTS/CTS） | なし |
| ソフトウェアフロー制御（XON/XOFF） | なし |
| ローカルエコー | 原則OFF |

公式ガイドはWindowsのMobaXtermと115200 bpsを例示している。
本書ではLinuxはpicocom、WindowsはMobaXterm、macOSはpicocomを使用する。

### Linuxでpicocomを使う

以下は**PC上**で実行する。APTとDNFは使用中のOSに対応する一方だけを使う。

```bash
# Ubuntu / Debian系PC
sudo apt-get update
sudo apt-get install -y picocom

# Fedora系PC
sudo dnf install -y picocom
```

アダプターのUSBをPCへ接続し、認識されたdeviceを調べる。

```bash
ls -l /dev/serial/by-id/
```

表示された対象アダプターの名前を指定する。以下の`実際のアダプター名`はその名前へ置き換える。
`/dev/serial/by-id/`がない環境では、接続時のkernelログから`/dev/ttyUSB0`や`/dev/ttyACM0`等を特定する。
複数アダプターがある場合に番号だけで判断しない。

```bash
UART_DEV=/dev/serial/by-id/実際のアダプター名
UART_LOG="$PWD/jupiter2-uart-$(date +%Y%m%d-%H%M%S).log"
sudo picocom --baud 115200 --databits 8 --parity n --stopbits 1 --flow n \
    --logfile "$UART_LOG" "$UART_DEV"
```

端末を開いてからJupiter2を給電・起動する。
終了は`Ctrl+A`を押し、離してから`Ctrl+X`を押す。
ログは指定したPC上のファイルへ保存される。起動の識別情報等を含むため、作業用に管理する。

deviceへのアクセス権がある場合はsudo不要。同じポートを別の端末ソフトが開いていないことも確認する。

### WindowsでMobaXtermを使う

1. USB–UARTアダプターを接続し、必要ならメーカー提供のdriverを導入する。
2. デバイスマネージャーの「ポート（COMとLPT）」で対象のCOM番号を確認する。
3. MobaXtermの「Session」→「Serial」を開く。
4. 対象COM番号を選び、速度を115200にする。
5. 上表の8N1・フロー制御なしに合わせて接続する。
6. ターミナルのログ保存機能で保存先を選び、本体を起動する。

Tera TermやPuTTYでも、同じCOM番号と通信設定で接続できる。
COM番号は実際のアダプターを確認し、COM3等に固定しない。

### macOSでpicocomを使う

Homebrewを使用しているPCでは：

```bash
brew install picocom
ls /dev/cu.usb*
```

該当する`/dev/cu.usbserial-...`や`/dev/cu.usbmodem...`を指定する。

```bash
UART_DEV=/dev/cu.usbserial-実際の番号
picocom --baud 115200 --databits 8 --parity n --stopbits 1 --flow n \
    --logfile "$PWD/jupiter2-uart-$(date +%Y%m%d-%H%M%S).log" "$UART_DEV"
```

deviceが見えない場合はアダプターのmacOS対応とdriverを確認する。終了操作はLinuxと同じ。

## 4. 起動ログとキー入力を確認する

1. PCのシリアル端末を先に接続し、ログ保存を開始する。
2. Jupiter2を通常起動する。FDLボタンは押さない。
3. 電源投入直後から小文字の`s`を押し続ける、または繰り返し送る。
4. U-Bootプロンプトで止まったら、次を入力する。

```text
version
printenv knl_name ramdisk_name dtb_dir
```

出力が読め、入力したコマンドへ応答が返れば、送受信の両方を確認できる。
単にログが見えるだけではPC→基板側の送信経路を確認したことにはならない。

SpacemiTの[K3起動ガイド](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md)には、
起動時の`s`キーによるU-Bootコマンドラインへの入り方が記載されている。
実機のfirmware版によって停止キーや猶予時間が異なる場合は、UARTの表示とその版の設定を確認する。

**新kernelを配置・試験する前に、このU-Boot停止操作が使えることを確認する。**
初回の接続確認では`setenv`・`saveenv`・flash操作を行う必要はない。
接続確認後の新kernel試験は[インストール手順書の第7章](milkv-jupiter2-stack-install.md#7-試験用boot-entryを追加する)に従う。
RAM上の試験では`saveenv`を実行しない。

## 5. 接続できない場合

| 症状 | 確認すること |
| --- | --- |
| PCにserial device／COMが出ない | USBケーブル、変換アダプター、driver。Jupiter2のDRDポートだけにつないでいないか |
| ポートを開けない | アクセス権、別ソフトによる占有、指定deviceの誤り |
| 本体を起動しても文字が出ない | 基板TX→アダプターRX、GND、本体電源、対象UART端子 |
| 文字化けする | 115200/8N1、信号電圧、GND、配線 |
| ログは見えるがキーが効かない | アダプターTX→基板RX、フロー制御なし、フォーカス、起動直後からの送信 |
| sで停止せずLinuxへ進む | 操作のタイミングと対象U-Bootの停止キー。kernel設定を変える前に解決する |

配線を変更する場合は本体電源とアダプターUSBを外す。
UEFI版のF2操作、FDLによるUSB書込みモード、UARTでのU-Boot停止は別の操作である。

## 6. 参照資料と確認範囲

- [Milk-V Jupiter2 Quick Start](https://milkv.io/docs/jupiter2/getting-started/quick-start)：K3 Pico-ITXガイドへの公式参照。
- [SpacemiT K3 Pico-ITX User Guide PDF](https://cdn-resource.spacemit.com/file/product/K3/k3_pico_ug_en.pdf)：V1.4、2026-11-06。第2.1、3.2、5.2節。
- [K3 Pico-ITXガイドのHTML版](https://docs.bit-brick.com/docs/k3_pico/pico_user_guide)：接続写真とWindows設定例。
- [K3ハードウェア資料](https://docs.bit-brick.com/docs/k3_pico/pico_hw_resources)：基板revisionに対応する回路資料を確認する。
- [SpacemiT K3起動ガイド](https://github.com/spacemit-com/docs-buildroot/blob/main/en/k3_buildroot/device/boot.md)：U-Boot停止・起動手順。

公式接続図と資料に基づく手順。実機とPCを接続した動作確認は未実施。
