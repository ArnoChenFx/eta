#!/usr/bin/env python3
"""OpenHarmony 7.0 SDK compatibility patches for generated Eta HarmonyOS projects.

Subcommands:
  project <dir>   Stub Huawei HMS-only `@hms.*` imports, enable ArkWeb camera/microphone
                  permission requests, and link local ArkTS packages so OpenHarmony SDK
                  + hvigor can assemble an unsigned HAP.
"""

from __future__ import annotations

import pathlib
import sys


def replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if (new and new in text) or old not in text:
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_project(root: pathlib.Path) -> None:
    ets = root / "nsh/src/main/ets"

    (ets / "NativeShare.ets").write_text(
        """import { common } from "@kit.AbilityKit";
import type { SystemRequest, SystemReply } from "./NativeSystem";

export class NativeShare {
  async show(
    _context: common.UIAbilityContext,
    _key: number,
    _request: SystemRequest,
    _live: () => boolean,
  ): Promise<SystemReply> {
    return { phase: "dismissed", error: "systemShare is not available on OpenHarmony" };
  }
  cancel(_key: number): void {}
  close(): void {}
}
""",
        encoding="utf-8",
    )

    native_speech = ets / "NativeSpeech.ets"
    if native_speech.exists():
        native_speech.write_text(
            """import { common } from "@kit.AbilityKit";
import type { SystemReply } from "./NativeSystem";

export interface SpeechReply extends SystemReply {
  phase: "start" | "result" | "end";
  text?: string;
  final?: boolean;
  error?: string;
}

export class NativeSpeech {
  constructor(_context: common.UIAbilityContext) {}
  async start(
    _key: number,
    _language: string | undefined,
    _interim: boolean,
    reply: (event: SpeechReply) => void,
    _live?: () => boolean,
  ): Promise<void> {
    reply({ phase: "end", error: "not-supported" });
  }
  async stop(_key: number, _abort: boolean): Promise<void> {}
  close(): void {}
}
""",
            encoding="utf-8",
        )

    native_system = ets / "NativeSystem.ets"
    s = native_system.read_text(encoding="utf-8")
    s = s.replace(
        'const kit = await import("@hms.filemanagement.fileManagerService");',
        'throw new Error("moving files to trash is not supported on OpenHarmony");',
    )
    s = s.replace("trashedUri = await kit.default.deleteToTrash(uri);", 'trashedUri = "";')
    native_system.write_text(s, encoding="utf-8")

    native_desktop = ets / "NativeDesktop.ets"
    lines = native_desktop.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if "@hms.pcService.statusBarManager" in line:
            continue
        if "private async applySetTray(" in line:
            out.append("  private async applySetTray(_generation: number, _cmd: WireCommand): Promise<void> {}\n")
            out.append("  private async applyRemoveTray(): Promise<void> {}\n")
            out.append("  private removeTraySync(): void {}\n")
            out.append("  private unsubscribeTray(): void {}\n")
            out.append("}\n")
            break
        out.append(line)
    native_desktop.write_text("".join(out), encoding="utf-8")

    # Enable WebView camera/microphone permission requests (used by the QR code scanner).
    native_webviews = ets / "NativeWebViews.ets"
    replace_once(
        native_webviews,
        'import { FrameCallback, UIContext } from "@ohos.arkui.UIContext";',
        'import { abilityAccessCtrl, Permissions } from "@kit.AbilityKit";\nimport { FrameCallback, UIContext } from "@ohos.arkui.UIContext";',
    )
    replace_once(
        native_webviews,
        """      .onShowFileSelector((event): boolean => {
        if (!event) {
          return false;
        }
        this.entry.selectFiles(event.fileSelector, event.result);
        return true;
      })""",
        """      .mediaPlayGestureAccess(false)
      .onPermissionRequest((event) => {
        if (!event) {
          return;
        }
        this.entry.handlePermissionRequest(event.request);
      })
      .onShowFileSelector((event): boolean => {
        if (!event) {
          return false;
        }
        this.entry.selectFiles(event.fileSelector, event.result);
        return true;
      })""",
    )
    replace_once(
        native_webviews,
        "  selectFiles(selector: FileSelectorParam, result: FileSelectorResult): void {",
        """  handlePermissionRequest(request: PermissionRequest): void {
    const epoch = this.epoch;
    this.resolvePermissionRequest(request, epoch).catch((error: Error) => {
      console.warn(`NSH WebView permission request: ${String(error)}`);
      try {
        request.deny();
      } catch {}
    });
  }

  private async resolvePermissionRequest(
    request: PermissionRequest,
    epoch: number,
  ): Promise<void> {
    if (this.closed || !this.context.isActive() || epoch !== this.epoch) {
      request.deny();
      return;
    }
    const resources = request.getAccessibleResource();
    const permissions: Permissions[] = [];
    const grantedResources: string[] = [];
    for (const resource of resources) {
      if (resource === ProtectedResourceType.VIDEO_CAPTURE) {
        permissions.push("ohos.permission.CAMERA");
        grantedResources.push(resource);
      } else if (resource === ProtectedResourceType.AUDIO_CAPTURE) {
        permissions.push("ohos.permission.MICROPHONE");
        grantedResources.push(resource);
      }
    }
    if (permissions.length === 0) {
      request.deny();
      return;
    }
    const host = this.context.getUIContext().getHostContext();
    if (!host) {
      request.deny();
      return;
    }
    const result = await abilityAccessCtrl
      .createAtManager()
      .requestPermissionsFromUser(host, permissions);
    if (this.closed || !this.context.isActive() || epoch !== this.epoch) {
      request.deny();
      return;
    }
    const allowed: string[] = [];
    for (let i = 0; i < grantedResources.length; i += 1) {
      if (result.authResults[i] === 0) {
        allowed.push(grantedResources[i]);
      }
    }
    if (allowed.length > 0) {
      request.grant(allowed);
    } else {
      request.deny();
    }
  }

  selectFiles(selector: FileSelectorParam, result: FileSelectorResult): void {""",
    )

    # When `nsh package` runs with `--no-hap`, it skips linking local ArkTS packages.
    # Mirror `nsh-platform-harmonyos`'s `link_packages()` so `hvigor` resolves `@nsh/harmonyos`.
    entry_oh = root / "entry/oh_modules"
    links = [
        (entry_oh / "@nsh/harmonyos", (root / "nsh").resolve()),
        (
            entry_oh / "libnsh_platform_harmonyos.so",
            (root / "nsh/src/main/cpp/types/libnsh_platform_harmonyos").resolve(),
        ),
    ]
    for link_path, target_path in links:
        link_path.parent.mkdir(parents=True, exist_ok=True)
        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()
        link_path.symlink_to(target_path)


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 2 or args[0] != "project":
        print("usage: patch-harmonyos.py project <dir>", file=sys.stderr)
        return 2
    patch_project(pathlib.Path(args[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
