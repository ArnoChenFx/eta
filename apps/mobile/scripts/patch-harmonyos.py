#!/usr/bin/env python3
"""Compatibility patches for building apps/mobile with nsh 0.7.0 nightly and OpenHarmony 7.0 SDK.

Subcommands:
  platform <dir>   Patch an nsh-platform-harmonyos source checkout for nsh 0.7.0 APIs.
  project  <dir>   Stub Huawei HMS-only `@hms.*` imports in a generated OpenHarmony project
                   so OpenHarmony SDK + hvigor can assemble an unsigned HAP.
"""

from __future__ import annotations

import pathlib
import re
import sys


def replace_once(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if (new and new in text) or old not in text:
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_platform(root: pathlib.Path, nsh_rev: str | None = None) -> None:
    # 1. Cargo.toml: bump nsh-* workspace deps from 0.6 to 0.7 so [patch.crates-io] applies,
    #    and enable the `websocket` feature on `nsh-engine`.
    cargo = root / "Cargo.toml"
    text = cargo.read_text(encoding="utf-8")
    for old, new in [
        ('nsh-core = "0.6"', 'nsh-core = "0.7"'),
        ('nsh-engine = { version = "0.6", default-features = false }', 'nsh-engine = { version = "0.7", default-features = false }'),
        ('nsh-base = { version = "0.6", default-features = false }', 'nsh-base = { version = "0.7", default-features = false }'),
        ('nsh-package = "0.6"', 'nsh-package = "0.7"'),
        ('nsh-dev = "0.6"', 'nsh-dev = "0.7"'),
        ('nsh-testing = { version = "0.6", default-features = false }', 'nsh-testing = { version = "0.7", default-features = false }'),
        ('nsh-engine = { workspace = true, features = ["js"] }', 'nsh-engine = { workspace = true, features = ["js", "websocket"] }'),
    ]:
        text = text.replace(old, new)
    cargo.write_text(text, encoding="utf-8")

    if nsh_rev:
        lock = root / "Cargo.lock"
        if lock.exists():
            lock_text = lock.read_text(encoding="utf-8")
            lock_text = re.sub(
                r"(git\+https://github\.com/longbridge/nsh\?branch=main#)[0-9a-f]{40}",
                rf"\g<1>{nsh_rev}",
                lock_text,
            )
            lock.write_text(lock_text, encoding="utf-8")

    # 2. src/app/chunks.rs: Bundle::url_schemes removed in nsh 0.7.0.
    replace_once(
        root / "src/app/chunks.rs",
        """        if let Some(schemes) = manifest.get("schemes") {
            bundle.url_schemes = nsh_core::url_scheme::schemes_from_json(schemes);
        }
""",
        "",
    )

    # 3. src/app/runtime.rs: speech removed from Environment and EngineConfig in nsh 0.7.0.
    replace_once(
        root / "src/app/runtime.rs",
        "            speech: config.host.speech_available,\n",
        "",
    )
    replace_once(
        root / "src/app/runtime.rs",
        "            speech: None,\n",
        "",
    )

    # 4. src/input/editor.rs: InputConfig::replaced removed in nsh 0.7.0.
    replace_once(
        root / "src/input/editor.rs",
        "if self.config.borrow().replaced {",
        "if false {",
    )
    replace_once(
        root / "src/input/editor.rs",
        "scrollbar_visible: config.scrollbar_visible && !config.replaced,",
        "scrollbar_visible: config.scrollbar_visible,",
    )

    # 5. src/input/events.rs: EventPayload::Pan / PanCancelled gained `origin`.
    replace_once(
        root / "src/input/events.rs",
        """                                            EventPayload::PanCancelled {
                                                translation,""",
        """                                            EventPayload::PanCancelled {
                                                origin: nsh_core::Point::new(
                                                    nsh_core::Points(0.0),
                                                    nsh_core::Points(0.0),
                                                ),
                                                translation,""",
    )
    replace_once(
        root / "src/input/events.rs",
        """                                            EventPayload::Pan {
                                                translation,""",
        """                                            EventPayload::Pan {
                                                origin: nsh_core::Point::new(
                                                    nsh_core::Points(0.0),
                                                    nsh_core::Points(0.0),
                                                ),
                                                translation,""",
    )

    # 6. src/input/keyboard.rs: Modifiers gained `alt_graph`.
    replace_once(
        root / "src/input/keyboard.rs",
        """                explicit_modifiers: Some(Modifiers {
                    ctrl: event.ctrl,
                    alt: event.alt,
                    shift: event.shift,
                    cmd: event.cmd,
                }),""",
        """                explicit_modifiers: Some(Modifiers {
                    ctrl: event.ctrl,
                    alt: event.alt,
                    shift: event.shift,
                    cmd: event.cmd,
                    alt_graph: false,
                }),""",
    )
    replace_once(
        root / "src/input/keyboard.rs",
        """        Modifiers {
            ctrl: self.has(N::CtrlLeft, N::CtrlRight),
            alt: self.has(N::AltLeft, N::AltRight),
            shift: self.has(N::ShiftLeft, N::ShiftRight),
            cmd: self.has(N::MetaLeft, N::MetaRight),
        }""",
        """        Modifiers {
            ctrl: self.has(N::CtrlLeft, N::CtrlRight),
            alt: self.has(N::AltLeft, N::AltRight),
            shift: self.has(N::ShiftLeft, N::ShiftRight),
            cmd: self.has(N::MetaLeft, N::MetaRight),
            alt_graph: false,
        }""",
    )

    # 7. src/render/mount.rs: Command::Speech removed; TextLocale & OpenAppSettings added.
    replace_once(
        root / "src/render/mount.rs",
        "                        | Command::Speech(_)\n",
        "",
    )
    replace_once(
        root / "src/render/mount.rs",
        """                        Command::FileRequest { id, request } => {
                            self.host.system.file_request(
                                &self.host,
                                self.dispatcher.clone(),
                                id,
                                *request,
                            )?;
                        }
                    },""",
        """                        Command::FileRequest { id, request } => {
                            self.host.system.file_request(
                                &self.host,
                                self.dispatcher.clone(),
                                id,
                                *request,
                            )?;
                        }
                        Command::TextLocale(_) | Command::OpenAppSettings { .. } => {}
                    },""",
    )

    # 8. src/services/system.rs: remove nsh_core::speech references.
    system_rs = root / "src/services/system.rs"
    replace_once(
        system_rs,
        "use nsh_core::{notifications::NotificationCommand as N, speech::SpeechCommand as S};",
        "use nsh_core::notifications::NotificationCommand as N;",
    )
    s = system_rs.read_text(encoding="utf-8")
    s = re.sub(
        r"            Command::Speech\(command\) => \{.*?\n            \}\n",
        "",
        s,
        count=1,
        flags=re.DOTALL,
    )
    s = re.sub(
        r"        \} else if request\.kind == EventKind::Speech \{.*?\n        \} else \{",
        "        } else {",
        s,
        count=1,
        flags=re.DOTALL,
    )
    system_rs.write_text(s, encoding="utf-8")


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

    (ets / "NativeSpeech.ets").write_text(
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
    nsh_rev: str | None = None
    if "--nsh-rev" in args:
        idx = args.index("--nsh-rev")
        if idx + 1 >= len(args):
            print("error: --nsh-rev requires a commit SHA", file=sys.stderr)
            return 2
        nsh_rev = args[idx + 1]
        args = args[:idx] + args[idx + 2 :]
    if len(args) != 2 or args[0] not in ("platform", "project"):
        print("usage: patch-harmonyos.py <platform|project> <dir> [--nsh-rev SHA]", file=sys.stderr)
        return 2
    target = pathlib.Path(args[1])
    if args[0] == "platform":
        patch_platform(target, nsh_rev=nsh_rev)
    else:
        patch_project(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
