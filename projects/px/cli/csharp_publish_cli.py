# -*- coding: utf-8 -*-
import os
import argparse
import logging

from projects.px.workflows.csharp_publish import run_csharp_publish
from core.build_context import init_from_env, set_build_context

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    ctx = init_from_env()

    parser = argparse.ArgumentParser(
        prog="csharp_publish_cli", description="Git -> SVN -> Build -> Commit")
    parser.add_argument("--git-repo", required=True)
    parser.add_argument("--git-branch", required=True)

    parser.add_argument(
        "--git-dir", default=os.path.join(ctx.workspace or ".", "_git"))

    parser.add_argument("--sln", required=True,
                        help="sln path (relative to svn_workspace or absolute)")
    parser.add_argument("--release", action="store_true",
                        help="use Release configuration (default Debug)")

    # 你不想要 trigger-type，那就用 build-note（兼容 COMMENT）
    parser.add_argument("--build-note", default="",
                        help="build note / reason (prefer BUILD_NOTE env)")

    parser.add_argument("--force", action="store_true",
                        help="force build even if git no changes")
    parser.add_argument("--ssh-key", default="", help="optional ssh key path")

    args = parser.parse_args()

    configuration = "Release" if args.release else "Debug"

    run_csharp_publish(
        git_repo=args.git_repo,
        git_branch=args.git_branch,
        git_dir=args.git_dir,
        map_from=args.map_from,
        map_to=args.map_to,
        sln_path=args.sln,
        configuration=configuration,
        force=args.force,
        ssh_key=(args.ssh_key or None),
    )


if __name__ == "__main__":
    main()
