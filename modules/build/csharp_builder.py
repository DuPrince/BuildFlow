# -*- coding: utf-8 -*-

import os
import subprocess
import logging

# 模块级日志（由 CLI / mainbuild 决定 handler）
logger = logging.getLogger(__name__)


class CSharpBuildResult:
    """
    C# 编译结果（结构化返回）
    """

    def __init__(
        self,
        success: bool,
        returncode: int,
        stdout: str,
        stderr: str,
        command: str,
        project_path: str,
    ):
        self.success = success
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.command = command
        self.project_path = project_path

    def __bool__(self):
        return self.success


def build_csharp(
    msbuild_path: str,
    project_path: str,
    configuration: str = "Release",
    restore: bool = True,
    rebuild: bool = True,
) -> CSharpBuildResult:
    """
    纯 C# 工程编译（模块级能力）

    - 不 exit
    - 不关心 Jenkins / Git / SVN
    - 通过返回值判断成功或失败
    """

    logger.info("========== CSharp Build Start ==========")
    logger.info("MSBuild      : %s", msbuild_path)
    logger.info("Project      : %s", project_path)
    logger.info("Configuration: %s", configuration)
    logger.info("Restore      : %s", restore)
    logger.info("Rebuild      : %s", rebuild)

    # ---------- 参数校验 ----------
    if not os.path.isfile(msbuild_path):
        error_msg = f"MSBuild not found: {msbuild_path}"
        logger.error(error_msg)
        return CSharpBuildResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=error_msg,
            command="",
            project_path=project_path,
        )

    if not os.path.exists(project_path):
        error_msg = f"Project not found: {project_path}"
        logger.error(error_msg)
        return CSharpBuildResult(
            success=False,
            returncode=-1,
            stdout="",
            stderr=error_msg,
            command="",
            project_path=project_path,
        )

    # ---------- 组装 MSBuild 命令 ----------
    targets = []
    if restore:
        targets.append("Restore")
    targets.append("Rebuild" if rebuild else "Build")

    target_arg = "/t:" + ";".join(targets)
    prop_arg = f"/p:Configuration={configuration}"

    command = (
        f"\"{msbuild_path}\" "
        f"\"{project_path}\" "
        f"{target_arg} "
        f"{prop_arg}"
    )

    logger.info("Execute CMD  : %s", command)

    # ---------- 执行 ----------
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    stdout, stderr = process.communicate()
    returncode = process.returncode

    if stdout:
        logger.info("----- MSBuild STDOUT -----")
        logger.info(stdout)

    if stderr:
        logger.error("----- MSBuild STDERR -----")
        logger.error(stderr)

    success = returncode == 0

    if success:
        logger.info("========== CSharp Build SUCCESS ==========")
    else:
        logger.error(
            "========== CSharp Build FAILED (code=%s) ==========",
            returncode,
        )

    return CSharpBuildResult(
        success=success,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        command=command,
        project_path=project_path,
    )
