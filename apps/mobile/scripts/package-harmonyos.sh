#!/bin/sh
# Package Eta mobile (`apps/mobile`) for HarmonyOS / OpenHarmony.
#
# Usage:
#   scripts/package-harmonyos.sh                      # unsigned/debug-signed HAP (OpenHarmony)
#   scripts/package-harmonyos.sh --runtime-os harmonyos
#   scripts/package-harmonyos.sh --no-hap             # write DevEco Studio project only
#
# Environment:
#   OHOS_NDK_HOME       OpenHarmony NDK directory (contains `native/`), API 20+
#   DEVECO_STUDIO_HOME  DevEco Studio or HarmonyOS CLI tools (for HarmonyOS HAP)
#   OHOS_BASE_SDK_HOME  OpenHarmony SDK root (e.g. ~/ohos-sdk with 26.0.0/) when not using DevEco
#   HVIGOR_HOME         npm prefix containing @ohos/hvigor and @ohos/hvigor-ohos-plugin
#   NSH_HARMONYOS_SOURCE Optional local checkout of nsh-platform-harmonyos
set -eu

cd "$(dirname "$0")/.."

# Build outside the monorepo root by default so hvigor's `npm config list`
# does not trip over the workspace root's `package.json` (`ENOWORKSPACES`).
out_dir="${ETA_HARMONYOS_OUT:-/tmp/eta-mobile-harmonyos-out}"
mkdir -p .nsh/out

nsh package App.tsx --target harmonyos -o "$out_dir" "$@"

hap="$(find "$out_dir/entry/build" -type f -name '*.hap' 2>/dev/null | head -n 1 || true)"
if [ -n "$hap" ]; then
  dest=".nsh/out/$(basename "$hap")"
  cp "$hap" "$dest"
  echo "$dest"
fi
