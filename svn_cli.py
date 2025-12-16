# -*- coding: utf-8 -*-
"""
svn_cli.py

基于 svn_ops 的命令行工具。
用于本地调试 / Jenkins / CI 调用。

示例：

    python svn_cli.py info --repo E:\\Works\\Proj

    python svn_cli.py checkout \
        --url https://svn.xxx.com/proj/trunk \
        --repo E:\\Works\\Proj

    python svn_cli.py ensure-workspace \
        --url https://svn.xxx.com/proj/trunk \
        --repo E:\\Works\\Proj \
        --profile csharp_build

    python svn_cli.py update --repo E:\\Works\\Proj --revision HEAD
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import json
from typing import List

from modules.vcs.svn_ops import SvnOps, VCSException


# ----------------------------------------------------------------------
# 工具函数
# ----------------------------------------------------------------------

def build_ops(repo: str) -> SvnOps:
    """
    创建 SvnOps 实例，并简单检查路径。
    """
    if not repo:
        raise VCSException("缺少 --repo 参数。")
    if not os.path.isdir(repo):
        raise VCSException(f"repo 路径不存在: {repo}")
    return SvnOps(repo)


def load_sparse_profile(profile_path: str) -> dict:
    """
    加载 SVN sparse profile（JSON）
    """

    if not os.path.isfile(profile_path):
        raise VCSException(f"sparse profile 不存在: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------
# 子命令实现
# ----------------------------------------------------------------------

def cmd_info(args: argparse.Namespace):
    ops = build_ops(args.repo)
    url = ops.get_current_url()
    rev = ops.get_current_revision()
    print("URL :", url)
    print("REV :", rev)


def cmd_checkout(args: argparse.Namespace):
    ops = SvnOps(args.repo)
    ops.checkout(args.url, args.revision)
    print("Checkout 完成。")


def cmd_ensure_workspace(args: argparse.Namespace):
    """
    确保工作副本符合 sparse profile 描述的状态
    """
    ops = SvnOps(args.repo)
    profile = load_sparse_profile(args.profile)

    ops.ensure_sparse_workspace(
        sparse_profile=profile,
    )

    print(f"Workspace 已对齐 sparse profile: {args.profile}")


def cmd_update(args: argparse.Namespace):
    ops = build_ops(args.repo)
    ops.update_to(args.revision)

    print("Update 完成。")
    print("From rev:", ops.before_update_rev)
    print("To   rev:", ops.after_update_rev)

    if args.show_changes:
        result = ops.collect_update_result(
            include_diff=False,
            include_externals=True,
        )
        print("\n本次更新变更列表：")
        for rev in result.revision_changes:
            print(f"[r{rev.revision}] {rev.author} {rev.date}")
            print(f"  {rev.message}")
            for f in rev.files:
                print(f"    {f.action} {f.path}")


def cmd_switch(args: argparse.Namespace):
    ops = build_ops(args.repo)
    ops.switch_to(args.url, args.revision)
    print("Switch 完成。")


def cmd_clean(args: argparse.Namespace):
    ops = build_ops(args.repo)
    ops.ensure_clean_workspace()
    print("工作副本已清理干净。")


def cmd_update_paths(args: argparse.Namespace):
    ops = build_ops(args.repo)
    if not os.path.isfile(args.json):
        raise VCSException(f"JSON 文件不存在: {args.json}")
    ops.update_paths_from_json(args.json)
    print("指定路径已更新到对应版本。")


def cmd_summary(args: argparse.Namespace):
    ops = build_ops(args.repo)
    summary = ops.collect_change_summary(
        start_time=args.start_time,
        end_time=args.end_time,
        include_diff=False,
        include_externals=not args.no_ext,
    )

    print("主仓库变更：")
    for rev in summary["main"]:
        print(f"[r{rev.revision}] {rev.author} {rev.date}")
        print(f"  {rev.message}")
        for f in rev.files:
            print(f"    {f.action} {f.path}")

    if summary["ext"]:
        print("\nExternal 仓库变更：")
        for url, lst in summary["ext"].items():
            print(f"\n== {url} ==")
            for rev in lst:
                print(f"[r{rev.revision}] {rev.author} {rev.date}")
                print(f"  {rev.message}")
                for f in rev.files:
                    print(f"    {f.action} {f.path}")


# ----------------------------------------------------------------------
# 主入口
# ----------------------------------------------------------------------

def main(argv: List[str] = None):
    if argv is None:
        argv = sys.argv[1:]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="SvnOps 命令行工具"
    )
    sub = parser.add_subparsers(dest="cmd")

    # info
    p = sub.add_parser("info", help="显示 URL 和 revision")
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.set_defaults(func=cmd_info)

    # checkout
    p = sub.add_parser("checkout", help="普通检出")
    p.add_argument("--url", required=True, help="仓库 URL")
    p.add_argument("--repo", required=True, help="检出到的本地路径")
    p.add_argument("--revision", default=None, help="目标 revision")
    p.set_defaults(func=cmd_checkout)

    # ensure-workspace（NEW，唯一的 sparse 入口）
    p = sub.add_parser(
        "ensure-workspace",
        help="确保工作副本符合 sparse profile 描述的状态",
    )
    p.add_argument("--url", required=True, help="仓库 URL")
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.add_argument(
        "--profile",
        required=True,
        help="sparse profile 名称（不含 .json）",
    )
    p.set_defaults(func=cmd_ensure_workspace)

    # update
    p = sub.add_parser("update", help="更新到指定版本")
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.add_argument("--revision", default=None, help="目标 revision")
    p.add_argument(
        "--show-changes",
        action="store_true",
        help="更新完成后打印本次变更明细",
    )
    p.set_defaults(func=cmd_update)

    # switch
    p = sub.add_parser("switch", help="切换 URL / 分支")
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.add_argument("--url", required=True, help="目标 URL")
    p.add_argument("--revision", default=None, help="目标 revision")
    p.set_defaults(func=cmd_switch)

    # clean
    p = sub.add_parser("clean", help="回退本地修改并 cleanup")
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.set_defaults(func=cmd_clean)

    # update-paths
    p = sub.add_parser(
        "update-paths",
        help="按照 JSON 规则更新指定路径到指定版本",
    )
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.add_argument("--json", required=True, help="路径与版本映射 JSON")
    p.set_defaults(func=cmd_update_paths)

    # summary
    p = sub.add_parser(
        "summary",
        help="按时间区间收集变更（主仓库 + external）",
    )
    p.add_argument("--repo", required=True, help="工作副本路径")
    p.add_argument(
        "--start-time",
        default=None,
        help="起始时间",
    )
    p.add_argument(
        "--end-time",
        default=None,
        help="终止时间",
    )
    p.add_argument(
        "--no-ext",
        action="store_true",
        help="不收集 external 变更",
    )
    p.set_defaults(func=cmd_summary)

    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    try:
        args.func(args)
        return 0
    except VCSException as e:
        print(f"[SVN 错误] {e}")
        return 1
    except Exception as e:
        print(f"[未预期异常] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
