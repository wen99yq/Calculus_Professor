#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""calculus-professor — 学习档案初始化脚本。

从 templates/ 复制模板，在当前工作目录下生成学习档案骨架。
幂等：已存在的文件不会被覆盖。

用法:
  python create_archive.py
  python create_archive.py --root "微积分学习"
  python create_archive.py --force         # 覆盖已存在文件（慎用）
  python create_archive.py --dry-run       # 只列出将要创建的内容
"""

import argparse
import os
import shutil
import sys

RET_OK = 0
RET_ERROR = 1

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(SKILL_DIR, "templates")

DEFAULT_ROOT = "微积分学习"

DIRS = [
    (),
    ("笔记",),
    ("笔记", "知识卡片"),
    ("笔记", "知识地图"),
    ("报告",),
    ("学习计划_历史",),
]

FILES = [
    ("学生档案.template.md", "学生档案.md"),
    ("错题本.template.md", "错题本.md"),
    ("学习计划.template.md", "学习计划.md"),
    ("进度追踪.template.md", "进度追踪.md"),
]


def create(root, force=False, dry_run=False):
    root = os.path.normpath(os.path.expanduser(root))
    created_dirs, created_files, skipped = [], [], []

    for d in DIRS:
        target = os.path.join(root, *d) if d else root
        if os.path.isdir(target):
            skipped.append(target + os.sep)
            continue
        if dry_run:
            created_dirs.append(target + os.sep)
            continue
        try:
            os.makedirs(target, exist_ok=True)
            created_dirs.append(target + os.sep)
        except OSError as exc:
            print("创建目录失败：%s（%s）" % (target, exc), file=sys.stderr)
            return RET_ERROR, created_dirs, created_files, skipped

    for tpl, dest in FILES:
        src = os.path.join(TEMPLATE_DIR, tpl)
        dst = os.path.join(root, dest)
        if not os.path.isfile(src):
            print("警告：模板缺失 %s，跳过 %s" % (src, dest), file=sys.stderr)
            continue
        if os.path.isfile(dst) and not force:
            skipped.append(dst)
            continue
        if dry_run:
            created_files.append(dst)
            continue
        try:
            shutil.copyfile(src, dst)
            created_files.append(dst)
        except OSError as exc:
            print("写入失败：%s（%s）" % (dst, exc), file=sys.stderr)
            return RET_ERROR, created_dirs, created_files, skipped

    return RET_OK, created_dirs, created_files, skipped


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="create_archive.py",
        description="初始化微积分学习档案骨架（幂等，不覆盖已有文件）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--root", default=DEFAULT_ROOT, help="档案根目录，默认 微积分学习")
    p.add_argument("--force", action="store_true", help="覆盖已存在的档案文件（慎用）")
    p.add_argument("--dry-run", action="store_true", help="只显示将创建的内容，不实际写入")
    args = p.parse_args(argv)

    code, dirs, files, skipped = create(args.root, force=args.force, dry_run=args.dry_run)

    prefix = "[dry-run] " if args.dry_run else ""
    root = os.path.normpath(os.path.expanduser(args.root))
    print("%s档案根目录：%s" % (prefix, root))
    if dirs:
        print("\n%s新建目录 %d 个：" % (prefix, len(dirs)))
        for d in dirs:
            print("  + %s" % d)
    if files:
        print("\n%s新建文件 %d 个：" % (prefix, len(files)))
        for f in files:
            print("  + %s" % f)
    if skipped:
        print("\n已存在，跳过 %d 项（未覆盖）：" % len(skipped))
        for s in skipped:
            print("  = %s" % s)
    if not dirs and not files:
        print("\n档案已就绪，无需改动。")

    if code != RET_OK:
        print("\n[ERROR] 初始化过程中出现错误，请检查上面的提示。", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
