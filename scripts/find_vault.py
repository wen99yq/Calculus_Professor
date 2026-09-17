#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Calculus_Professor — Obsidian Vault 探测脚本（自包含，不依赖外部 obsidian skill）。

探测优先级:
  1. 本 skill 目录下 config.json 的 vault_path
  2. 环境变量 CALCULUS_VAULT
  3. 系统 obsidian.json 中 open=true 的库（跨平台）
  4. 备份策略：返回回退目录 微积分学习/笔记/

用法:
  python find_vault.py                       # 人类可读输出
  python find_vault.py --json                # 机器可读输出
  python find_vault.py --set "D:\\MyVault"    # 手动指定并写入 config.json
  python find_vault.py --notes-subdir 微积分  # 自定义 vault 内笔记子目录
"""

import argparse
import json
import os
import sys

RET_OK = 0
RET_ERROR = 1
RET_FALLBACK = 3

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")
DEFAULT_NOTES_SUBDIR = "微积分"
FALLBACK_NOTES_DIR = os.path.join("微积分学习", "笔记")


def read_config():
    if not os.path.isfile(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:  # noqa: BLE001
        print("写入 config.json 失败：%s" % exc, file=sys.stderr)
        return False


def obsidian_config_paths():
    home = os.path.expanduser("~")
    candidates = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "obsidian", "obsidian.json"))
        candidates.append(os.path.join(home, "AppData", "Roaming", "obsidian", "obsidian.json"))
    else:
        candidates.append(
            os.path.join(home, "Library", "Application Support", "obsidian", "obsidian.json")
        )
        xdg = os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config"))
        candidates.append(os.path.join(xdg, "obsidian", "obsidian.json"))
        candidates.append(
            os.path.join(
                home, ".var", "app", "md.obsidian.Obsidian", "config", "obsidian", "obsidian.json"
            )
        )
    out = []
    for p in candidates:
        if p and p not in out:
            out.append(p)
    return out


def scan_obsidian_vaults():
    """返回 (vault_path, 来源说明) 或 (None, 原因列表)。"""
    notes = []
    for cfg in obsidian_config_paths():
        if not os.path.isfile(cfg):
            notes.append("未找到 %s" % cfg)
            continue
        try:
            with open(cfg, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            notes.append("%s 解析失败（%s），已跳过" % (cfg, exc))
            continue

        vaults = data.get("vaults") if isinstance(data, dict) else None
        if not isinstance(vaults, dict):
            notes.append("%s 中没有 vaults 字段" % cfg)
            continue

        entries = []
        for vid, info in vaults.items():
            if not isinstance(info, dict):
                continue
            path = info.get("path")
            if not path:
                continue
            path = os.path.normpath(os.path.expanduser(path))
            entries.append(
                {
                    "id": vid,
                    "path": path,
                    "open": bool(info.get("open")),
                    "ts": int(info.get("ts") or 0),
                    "exists": os.path.isdir(path),
                }
            )

        if not entries:
            notes.append("%s 中没有任何 vault 条目" % cfg)
            continue

        usable = [e for e in entries if e["exists"]]
        missing = [e for e in entries if not e["exists"]]
        for e in missing:
            notes.append("vault 目录不存在，已忽略：%s" % e["path"])

        if not usable:
            notes.append("%s 中的 vault 目录全部不存在" % cfg)
            continue

        opened = [e for e in usable if e["open"]]
        pool = opened if opened else usable
        pool.sort(key=lambda e: e["ts"], reverse=True)
        best = pool[0]
        why = "open=true" if best["open"] else "按 ts 取最新"
        return best["path"], notes + ["来源：%s（%s）" % (cfg, why)]

    return None, notes


def resolve(vault_override=None):
    """按优先级解析笔记根目录。返回 dict。"""
    if vault_override:
        path = os.path.normpath(os.path.expanduser(vault_override))
        if os.path.isdir(path):
            return {
                "found": True,
                "vault": path,
                "source": "命令行 --set 指定",
                "notes_dir": os.path.join(path, DEFAULT_NOTES_SUBDIR),
                "notes": [],
            }
        return {
            "found": False,
            "vault": None,
            "source": "命令行 --set 指定的目录不存在",
            "notes_dir": FALLBACK_NOTES_DIR,
            "notes": ["指定路径不是有效目录：%s" % path],
        }

    cfg = read_config()
    if cfg.get("vault_path"):
        path = os.path.normpath(os.path.expanduser(str(cfg["vault_path"])))
        if os.path.isdir(path):
            return {
                "found": True,
                "vault": path,
                "source": "config.json 的 vault_path",
                "notes_dir": os.path.join(path, DEFAULT_NOTES_SUBDIR),
                "notes": [],
            }
        return {
            "found": False,
            "vault": None,
            "source": "config.json 中的 vault_path 已失效",
            "notes_dir": FALLBACK_NOTES_DIR,
            "notes": ["config.json 指向的目录不存在：%s" % path],
        }

    env_vault = os.environ.get("CALCULUS_VAULT")
    if env_vault:
        path = os.path.normpath(os.path.expanduser(env_vault))
        if os.path.isdir(path):
            return {
                "found": True,
                "vault": path,
                "source": "环境变量 CALCULUS_VAULT",
                "notes_dir": os.path.join(path, DEFAULT_NOTES_SUBDIR),
                "notes": [],
            }
        return {
            "found": False,
            "vault": None,
            "source": "环境变量 CALCULUS_VAULT 指向的目录不存在",
            "notes_dir": FALLBACK_NOTES_DIR,
            "notes": ["CALCULUS_VAULT=%s 不是有效目录" % path],
        }

    vault, notes = scan_obsidian_vaults()
    if vault:
        return {
            "found": True,
            "vault": vault,
            "source": notes[-1].replace("来源：", "") if notes else "obsidian.json",
            "notes_dir": os.path.join(vault, DEFAULT_NOTES_SUBDIR),
            "notes": notes,
        }
    return {
        "found": False,
        "vault": None,
        "source": "未找到",
        "notes_dir": FALLBACK_NOTES_DIR,
        "notes": notes,
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="find_vault.py",
        description="探测 Obsidian 库位置（跨平台，自包含）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--json", action="store_true", help="以 JSON 输出")
    p.add_argument("--set", metavar="PATH", help="手动指定 vault 路径并写入 config.json")
    p.add_argument("--notes-subdir", default=DEFAULT_NOTES_SUBDIR, help="vault 内笔记子目录名")
    p.add_argument("--show-config", action="store_true", help="打印 config.json 路径与内容")
    args = p.parse_args(argv)

    if args.show_config:
        print("config 路径: %s" % CONFIG_PATH)
        print(json.dumps(read_config(), ensure_ascii=False, indent=2))
        return RET_OK

    if args.set:
        target = os.path.normpath(os.path.expanduser(args.set))
        if not os.path.isdir(target):
            print("[ERROR] 目录不存在：%s" % target, file=sys.stderr)
            print("        请确认路径后重试；未写入 config.json。", file=sys.stderr)
            return RET_ERROR
        data = read_config()
        data["vault_path"] = target
        data.setdefault("notes_subdir", args.notes_subdir)
        if not write_config(data):
            return RET_ERROR
        print("[OK] 已记录 vault 路径：%s" % target)
        print("     config: %s" % CONFIG_PATH)
        print("     笔记将写入：%s" % os.path.join(target, args.notes_subdir))
        return RET_OK

    result = resolve()
    if result["found"]:
        result["notes_dir"] = os.path.join(result["vault"], args.notes_subdir)
    else:
        result["notes_dir"] = FALLBACK_NOTES_DIR

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return RET_OK if result["found"] else RET_FALLBACK

    if result["found"]:
        print("[OK] 找到 Obsidian 库：%s" % result["vault"])
        print("     来源：%s" % result["source"])
        print("     笔记将写入：%s" % result["notes_dir"])
        return RET_OK

    print("[FALLBACK] 未找到 Obsidian 库")
    print("     笔记将写入：%s" % result["notes_dir"])
    print("     提示：可以告诉我你的 Obsidian 库路径，我会记到 config.json 里")
    for n in result["notes"]:
        print("     诊断：%s" % n)
    return RET_FALLBACK


if __name__ == "__main__":
    sys.exit(main())
