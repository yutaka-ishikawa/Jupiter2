#!/usr/bin/env bash
set -Eeuo pipefail
bundle=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
cd "$bundle"
sha256sum -c SHA256SUMS
