#!/bin/sh
# 目的: 実Linux guestのPID1として、実driver/SDK/Eyrie/sampleのOCALLを検査する。
# rootfsにはBusyBox、runnerに対応するRISC-V共有ライブラリー、/tests/hello*、
# 対応kernelで作った/lib/modules/keystone-driver.koが必要。
# CPU3/8へ固定して各sampleを逐次実行し、失敗時は後続へ進まずログを出す。
# SBI/PMP/CSRのモックは使わない。開発PCの通常shellでは実行しない。
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
echo "KSB073-SAMPLES: START"
uname -r
echo "KSB073-SAMPLES: ONLINE $(cat /sys/devices/system/cpu/online)"
if ! insmod /lib/modules/keystone-driver.ko; then
 echo "KSB073-SAMPLES: FAIL DRIVER"
 poweroff -f
fi
ls -l /dev/keystone_enclave
for cpu in 3 8; do
for name in hello hello-native; do
 cd /tests/$name
 echo "KSB073-SAMPLES: RUN $name cpu=$cpu"
 taskset -c "$cpu" ./$name-runner $name eyrie-rt loader.bin
 result=$?
 echo "KSB073-SAMPLES: EXIT $name cpu=$cpu $result"
 if [ "$result" != 0 ]; then
  dmesg | tail -n 60
  echo "KSB073-SAMPLES: FAIL $name"
  poweroff -f
 fi
done
done
echo "KSB073-SAMPLES: PASS ALL"
dmesg | tail -n 30
poweroff -f
