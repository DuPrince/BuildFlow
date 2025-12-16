# -*- coding: utf-8 -*-

import argparse
import logging
import sys

from modules.build.csharp_builder import build_csharp

# CLI 级日志配置（统一入口）
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Pure C# build command (MSBuild wrapper)"
    )

    parser.add_argument(
        "--msbuild",
        required=True,
        help="Path to MSBuild.exe",
    )

    parser.add_argument(
        "--project",
        required=True,
        help="Path to .sln or .csproj",
    )

    parser.add_argument(
        "--config",
        default="Release",
        help="Build configuration (default: Release)",
    )

    parser.add_argument(
        "--restore",
        choices=["true", "false"],
        default="true",
        help="Whether to run Restore target (default: true)",
    )

    parser.add_argument(
        "--rebuild",
        choices=["true", "false"],
        default="true",
        help="Whether to use Rebuild target (default: true)",
    )

    return parser.parse_args()


def str2bool(value: str) -> bool:
    return value.lower() == "true"


def main():
    args = parse_args()

    logger.info("========== CSharp Build CLI ==========")

    result = build_csharp(
        msbuild_path=args.msbuild,
        project_path=args.project,
        configuration=args.config,
        restore=str2bool(args.restore),
        rebuild=str2bool(args.rebuild),
    )

    if not result:
        logger.error("CSharp build failed")
        logger.error("Command: %s", result.command)
        sys.exit(result.returncode if result.returncode != 0 else 1)

    logger.info("CSharp build finished successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
