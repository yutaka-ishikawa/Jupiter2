#!/usr/bin/env bash
# Install Linux and apps on the target board.
set -Eeuo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
[[ $(uname -m) == riscv64 && $EUID == 0 ]] || { echo 'Run with sudo on the Milk-V riscv64 board.' >&2; exit 2; }
bash "$bundle/tools/preflight.sh"
release=$(cat "$bundle/kernelrelease.txt")
case "$release" in ''|.|..|*[!A-Za-z0-9._+-]*) exit 2;; esac

test -s "$bundle/linux/Image"
test -s "$bundle/linux/config"
test -s "$bundle/modules/$release/extra/keystone-driver.ko"
test -s "$bundle/apps/hello.ke"
test -s "$bundle/apps/hello-native.ke"

app_dir="/opt/keystone/$release"
if [[ -L /opt/keystone || ( -e /opt/keystone && ! -d /opt/keystone ) ]]; then
    printf 'エラー: /opt/keystone は通常のディレクトリである必要があります。\n' >&2
    exit 2
fi
paths=("/boot/Image-$release-keystone" "/boot/config-$release-keystone" "/lib/modules/$release")
if [[ -d "$app_dir" && ! -L "$app_dir" ]]; then
    paths+=("$app_dir/hello.ke" "$app_dir/hello-native.ke")
else
    paths+=("$app_dir")
fi

declare -A existing keep saved
stages=()
installed=()
created_app_parent=
complete=no
for path in "${paths[@]}"; do
    if [[ -e "$path" || -L "$path" ]]; then
        existing[$path]=yes
        printf '%s を上書きしますか？ [y/N] ' "$path" >&2
        read -r answer && [[ "$answer" == [yY] ]] || { echo 'インストールを中止しました。' >&2; exit 1; }
        printf '%s のバックアップを残しますか？ [Y/n] ' "$path" >&2
        read -r answer || exit 1
        case "$answer" in
            ''|y|Y) keep[$path]=yes ;;
            n|N) keep[$path]=no ;;
            *) echo 'インストールを中止しました。' >&2; exit 1 ;;
        esac
    fi
done

cleanup() {
    local status=$? index path stage
    trap - EXIT
    if [[ "$complete" == no ]]; then
        for ((index=${#installed[@]}-1; index>=0; index--)); do
            path=${installed[index]}
            rm -rf -- "$path" || status=1
        done
        for path in "${!saved[@]}"; do
            if ! mv -T -- "${saved[$path]}" "$path"; then
                printf '復元に失敗しました。旧ファイルの退避先: %s\n' "${saved[$path]}" >&2
                status=1
            fi
        done
    fi
    for stage in "${stages[@]}"; do
        rm -rf -- "$stage/new" || status=1
        rmdir -- "$stage" 2>/dev/null || true
    done
    if [[ "$complete" == no && -n "$created_app_parent" ]]; then
        rmdir -- "$created_app_parent" 2>/dev/null || true
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! -d /opt/keystone ]]; then
    mkdir -- /opt/keystone
    created_app_parent=/opt/keystone
fi

for path in "${paths[@]}"; do
    stage=$(mktemp -d -- "${path%/*}/.install-linux.XXXXXX")
    stages+=("$stage")
    case "$path" in
        /boot/Image-*) install -m 0644 "$bundle/linux/Image" "$stage/new" ;;
        /boot/config-*) install -m 0644 "$bundle/linux/config" "$stage/new" ;;
        /lib/modules/*) cp -a -- "$bundle/modules/$release" "$stage/new" ;;
        "$app_dir")
            install -d "$stage/new"
            install -m 0755 "$bundle/apps/hello.ke" "$bundle/apps/hello-native.ke" "$stage/new/"
            ;;
        *) install -m 0755 "$bundle/apps/${path##*/}" "$stage/new" ;;
    esac
    if [[ ${existing[$path]:-no} == yes ]]; then
        backup="$path.backup-${stage##*.}"
        mv -T --no-clobber -- "$path" "$backup"
        if [[ -e "$path" || -L "$path" ]]; then
            printf '退避先が使用中です: %s\n' "$backup" >&2
            rm -rf -- "$stage/new"
            exit 1
        fi
        saved[$path]=$backup
        printf '旧ファイルの退避先: %s\n' "$backup"
    fi
    mv -T --no-clobber -- "$stage/new" "$path"
    if [[ -e "$stage/new" ]]; then
        printf '確認後に配置先が作成されました: %s\n' "$path" >&2
        rm -rf -- "$stage/new"
        exit 1
    fi
    installed+=("$path")
done

depmod -a "$release"
complete=yes
for path in "${paths[@]}"; do
    if [[ ${keep[$path]:-yes} == no ]]; then
        rm -rf -- "${saved[$path]}"
        printf '一時退避した旧ファイルを削除しました: %s\n' "${saved[$path]}"
    fi
done
printf 'OS files installed for %s. Generate or update initramfs using docs/milkv-jupiter2-stack-install.md.\n' "$release"
