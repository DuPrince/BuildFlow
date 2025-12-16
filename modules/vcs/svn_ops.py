# -*- coding: utf-8 -*-
"""
高性能 SVN 操作封装，面向大型游戏工程与构建系统。
支持：
- 更新前后版本号记录（可追踪变更范围）
- 稀疏检出（Sparse Checkout）
- 指定路径按指定版本回滚
- external 仓库变更统计
- 自动生成构建变更结果 UpdateResult
"""

from __future__ import annotations

import logging
import os
import subprocess
import shutil
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 基础异常类型
# ----------------------------------------------------------------------

class VCSException(Exception):
    """版本控制相关错误。"""
    pass


# ----------------------------------------------------------------------
# 用于记录变更的结构体
# ----------------------------------------------------------------------

@dataclass
class FileChange:
    """
    单个文件的变更信息。
    action:
        A = 新增
        M = 修改
        D = 删除
    diff:
        可选的 diff 内容（若开启 include_diff）
    """
    path: str
    action: str
    diff: Optional[str] = None


@dataclass
class RevisionChange:
    """
    单个 SVN revision 的变更信息。
    包含作者、时间、提交信息以及文件级别变更。
    """
    revision: str
    author: str
    date: str
    message: str
    files: List[FileChange]


@dataclass
class UpdateResult:
    """
    一次 update 的整体结果。
    from_rev：更新前的版本号
    to_rev：  更新后的版本号
    revision_changes：这次更新所有 revision 的变更详情
    """
    from_rev: str
    to_rev: str
    revision_changes: List[RevisionChange]


@dataclass
class SvnSparseProfile:
    name: str
    repo_url: str
    root_path: str
    root_depth: str
    paths: list

# ----------------------------------------------------------------------
# 统一命令执行函数
# ----------------------------------------------------------------------


def run_cmd(
    args: List[str],
    cwd: Optional[str] = None,
    check: bool = False,
) -> Tuple[int, str, str]:
    """
    执行命令行工具，并捕获 stdout / stderr。

    check=True 时表示遇到非 0 退出码会抛出异常。
    """
    if logger:
        logger.debug("执行命令: %s (cwd=%s)", " ".join(args), cwd)

    proc = subprocess.run(
        args,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False
    )

    out = proc.stdout or ""
    err = proc.stderr or ""

    if logger:
        logger.debug("退出码: %s", proc.returncode)
        if out.strip():
            logger.debug("STDOUT:\n%s", out)
        if err.strip():
            logger.debug("STDERR:\n%s", err)

    if check and proc.returncode != 0:
        raise VCSException(
            f"命令执行失败: {' '.join(args)}\n"
            f"退出码: {proc.returncode}\n"
            f"OUT:\n{out}\nERR:\n{err}"
        )

    return proc.returncode, out, err


# ----------------------------------------------------------------------
# SvnOps 主类
# ----------------------------------------------------------------------

class SvnOps:
    """
    高级 SVN 操作类，适用于大型仓库、multi-external、
    稀疏检出以及构建流水线自动化。
    """

    def __init__(self, repo_path: str):
        self.repo_path = repo_path

        # update_to 前后的版本号
        self.before_update_rev: Optional[str] = None
        self.after_update_rev: Optional[str] = None

    # ------------------------------------------------------------------
    # 内部封装 svn 命令，并处理工作副本锁定
    # ------------------------------------------------------------------

    def _svn(self, args: List[str], check: bool = False):
        """
        执行 svn 命令。
        若遇到工作副本锁定（E155004），会自动 cleanup 后再重试。
        """
        cmd = ["svn"] + args
        logger.info("执行 SVN 命令: %s", " ".join(cmd))
        code, out, err = run_cmd(
            cmd, cwd=self.repo_path, check=False
        )

        locked = (
            "is locked" in err
            or "E155004" in err
            or "run 'svn cleanup'" in err
        )

        if code != 0 and locked:
            logger.warning("工作副本被锁定，执行 cleanup 后重试。")
            self.cleanup(aggressive=False)
            code, out, err = run_cmd(
                cmd, cwd=self.repo_path, check=False
            )

        if check and code != 0:
            raise VCSException(
                f"svn 执行失败: {' '.join(cmd)}\n"
                f"退出码: {code}\nOUT:\n{out}\nERR:\n{err}"
            )

        return code, out, err
    # ------------------------------------------------------------------
    # 工作副本相关操作
    # ------------------------------------------------------------------

    def is_working_copy(self) -> bool:
        """
        判断 repo_path 是否是有效的 SVN 工作副本。
        """
        return os.path.isdir(os.path.join(self.repo_path, ".svn"))

    # ------------------------------------------------------------------
    # 回退本地修改 + 删除未版本控制文件
    # ------------------------------------------------------------------

    def revert_local_changes(self):
        """
        回退所有本地修改：
        1) svn revert -R .
        2) 删除未版本控制的文件（svn status 显示 ?）
        """
        logger.info("回退本地修改: %s", self.repo_path)

        # 回退版本控制下的所有修改
        self._svn(["revert", "-R", "."], check=False)

        # 查找未版本控制文件
        code, out, _ = self._svn(["status", "--no-ignore"], check=False)

        for line in out.splitlines():
            if not line.strip():
                continue

            status = line[0]
            path = line[8:].strip() if len(line) > 8 else ""

            if status != "?":
                continue
            if not path:
                continue

            full = os.path.join(self.repo_path, path)
            if os.path.isdir(full):
                logger.debug("删除未版本控制目录: %s", full)
                shutil.rmtree(full, ignore_errors=True)
            elif os.path.exists(full):
                logger.debug("删除未版本控制文件: %s", full)
                try:
                    os.remove(full)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # cleanup（处理锁定，修复结构）
    # ------------------------------------------------------------------

    def cleanup(self, aggressive: bool = False):
        """
        执行 svn cleanup，若 aggressive=True 则删除未版本控制和忽略项。
        """
        logger.info("执行 cleanup: %s (aggressive=%s)",
                    self.repo_path, aggressive)

        run_cmd(["svn", "cleanup"], cwd=self.repo_path)

        if aggressive:
            run_cmd(
                ["svn", "cleanup", "--remove-unversioned",
                 "--remove-ignored"],
                cwd=self.repo_path,
            )

    # ------------------------------------------------------------------
    # 保证工作副本干净（回退修改 + cleanup）
    # ------------------------------------------------------------------

    def ensure_clean_workspace(self):
        """
        保证工作副本处于干净状态：
        - 回退本地修改
        - cleanup
        - external 工作副本也处理（下一部分详细）
        """
        self.revert_local_changes()
        self.cleanup(aggressive=False)

        # external 清理
        self.clean_externals()

    # ------------------------------------------------------------------
    # external 基本支持
    # ------------------------------------------------------------------

    def get_externals(self) -> List[str]:
        """
        获得当前工作副本中定义的 external 本地路径列表。
        不递归。
        """
        code, out, _ = self._svn(
            ["propget", "svn:externals", "-R"],
            check=False
        )

        exts = []
        for line in out.splitlines():
            if " - " in line:
                local = line.split(" - ", 1)[0].strip()
                exts.append(os.path.join(self.repo_path, local))
        return exts

    def get_all_externals(self) -> List[str]:
        """
        获得所有 external（递归）。
        """
        visited = set()
        result = []

        def scan(path: str):
            if path in visited:
                return
            visited.add(path)

            ops = SvnOps(path)
            ex = ops.get_externals()
            for e in ex:
                if os.path.isdir(e):
                    result.append(e)
                    scan(e)

        scan(self.repo_path)
        return result

    def clean_externals(self):
        """
        对所有 external 执行 ensure_clean_workspace。
        """
        for e in self.get_all_externals():
            if os.path.isdir(e):
                SvnOps(e).ensure_clean_workspace()

    # ------------------------------------------------------------------
    # 稀疏检出（Sparse Checkout）
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
# 稀疏检出（Sparse Checkout）
# ------------------------------------------------------------------

    def ensure_sparse_workspace(self, sparse_profile: dict):
        """
        Workspace 级别多仓库 checkout + 可选 sparse。
        所有 project 都是独立 SVN 仓库，不使用 external。
        """

        projects = sparse_profile.get("projects")
        if not isinstance(projects, dict):
            raise VCSException("profile 缺少 projects 或格式错误")

        for name, proj in projects.items():
            repo_url = proj.get("repo_url")
            root_path = proj.get("root_path")
            root_depth = proj.get("root_depth", "infinity")
            paths = proj.get("paths", [])

            if not repo_url or not root_path:
                raise VCSException(f"project {name} 缺少 repo_url 或 root_path")

            project_path = os.path.join(self.repo_path, root_path)
            ops = SvnOps(project_path)

            logger.info(
                "[svn][%s] checkout %s -> %s (depth=%s)",
                name, repo_url, project_path, root_depth
            )

            # --------------------------------------------------
            # 1. checkout 仓库根
            # --------------------------------------------------
            if not ops.is_working_copy():
                os.makedirs(project_path, exist_ok=True)
                ops._svn(
                    ["checkout", repo_url, project_path, "--depth", root_depth],
                    check=True
                )
            else:
                logger.info("[svn][%s] reuse existing working copy", name)

            # --------------------------------------------------
            # 2. sparse 展开（仅对本仓库）
            # --------------------------------------------------
            if not paths:
                continue

            # 显式规则兜底：按路径深度排序（父 → 子）
            def _depth(p: str) -> int:
                return p.strip("/").count("/")

            sorted_paths = sorted(
                paths,
                key=lambda x: _depth(x["path"])
            )

            for item in sorted_paths:
                rel = item["path"].strip("/")
                depth = item.get("depth", "infinity")

                logger.info(
                    "[svn][%s] expand %s (depth=%s)",
                    name, rel, depth
                )

                # ❗关键点：
                # - 使用相对路径
                # - 不 mkdir
                # - 不检查 os.path.exists
                ops._svn(
                    ["update", rel, "--depth", depth],
                    check=True
                )

    # ------------------------------------------------------------------
    # 基础 checkout
    # ------------------------------------------------------------------

    def checkout(self, url: str, revision: Optional[str] = None):
        """
        普通检出（非稀疏）。
        若目录已存在且是工作副本，则跳过。
        """
        if self.is_working_copy():
            logger.info("已是工作副本，跳过 checkout: %s",
                        self.repo_path)
            return

        base_dir = os.path.dirname(self.repo_path)
        cmd = ["checkout", url, self.repo_path]

        if revision:
            cmd += ["-r", revision]

        run_cmd(["svn"] + cmd, cwd=base_dir, check=True)

        # ------------------------------------------------------------------
    # 基础信息查询：URL / 当前 revision
    # ------------------------------------------------------------------

    def get_current_url(self) -> str:
        """
        获取当前工作副本对应的远端 URL。
        """
        code, out, _ = self._svn(["info", "--show-item", "url"],
                                 check=True)
        return out.strip()

    def get_current_revision(self) -> str:
        """
        获取当前工作副本的 revision 号。
        """
        code, out, _ = self._svn(
            ["info", "--show-item", "revision"],
            check=True
        )
        return out.strip()

    def get_rev_time(self, revision: str) -> str:
        """
        获取某个 revision 的提交时间。
        用于时间区间查询 external 日志。
        """
        code, out, _ = self._svn(
            ["log", "--xml", "-r", revision],
            check=True
        )

        root = ET.fromstring(out)
        entry = root.find("logentry")
        if entry is None:
            raise VCSException(f"无法获取 revision {revision} 的日期")

        date_text = entry.findtext("date", "").strip()
        return date_text

    # ------------------------------------------------------------------
    # update 到指定版本
    # ------------------------------------------------------------------

    def update_to(self, target: Optional[str] = None):
        """
        更新到指定版本（默认 HEAD）。
        会自动记录 before_update_rev 和 after_update_rev。
        """
        self.before_update_rev = self.get_current_revision()

        logger.info("更新工作副本到 %s", target or "HEAD")
        self.ensure_clean_workspace()

        if target is None or target.upper() == "HEAD":
            self._svn(["update"], check=True)
        else:
            self._svn(["update", "-r", target], check=True)

        self.after_update_rev = self.get_current_revision()

    # ------------------------------------------------------------------
    # switch 切换分支 / URL
    # ------------------------------------------------------------------

    def switch_to(self, url: str, revision: Optional[str] = None):
        """
        切换到指定 URL（分支、标签）。
        """
        cur = self.get_current_url()
        if cur == url:
            logger.info("URL 未变化，跳过 switch")
            return

        logger.info("切换分支: %s -> %s", cur, url)
        self.ensure_clean_workspace()

        cmd = ["switch", url]
        if revision:
            cmd += ["-r", revision]

        self._svn(cmd, check=True)

    # ------------------------------------------------------------------
    # 获取远端 HEAD revision（用于 external 回溯）
    # ------------------------------------------------------------------

    def get_remote_head_revision(self) -> str:
        """
        获取当前 URL 的远端最新 revision。
        """
        url = self.get_current_url()
        code, out, _ = self._svn(
            ["info", "--show-item", "revision", url],
            check=True
        )
        return out.strip()

    # ------------------------------------------------------------------
    # 指定路径回滚到指定 revision（版本 1 JSON）
    # ------------------------------------------------------------------

    def update_paths_to_revision(self, rules: List[dict]):
        """
        按 JSON 规则更新路径到指定 revision。
        JSON 单项示例：
            { "path": "px-data-output", "revision": "1200" }
        """
        for rule in rules:
            rel = rule.get("path")
            rev = rule.get("revision")

            if not rel or not rev:
                logger.warning("跳过非法规则: %s", rule)
                continue

            full = os.path.join(self.repo_path, rel)
            if not os.path.exists(full):
                logger.info("创建空目录: %s", full)
                os.makedirs(full, exist_ok=True)

            logger.info("路径更新: %s -> r%s", rel, rev)
            self._svn(
                ["update", rel, "-r", rev, "--depth=infinity"],
                check=True
            )

    def update_paths_from_json(self, json_path: str):
        """
        从 JSON 文件读取 path→revision 的规则，并执行更新。
        JSON 格式示例：
        {
            "paths": [
                {"path":"px","revision":"1200"}
            ]
        }
        """
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        rules = data.get("paths", [])
        if not isinstance(rules, list):
            raise VCSException("JSON 格式错误: paths 应为列表")

        self.update_paths_to_revision(rules)

    # ------------------------------------------------------------------
    # 获取 revision 区间的详细变更（含文件级别）
    # ------------------------------------------------------------------

    def get_revision_list(
        self,
        from_rev: Optional[str],
        to_rev: str
    ) -> List[RevisionChange]:
        """
        获取 revision 区间的提交记录（不含 diff）。
        返回 RevisionChange 列表。
        """
        rev_range = f"{from_rev}:{to_rev}" if from_rev else to_rev

        code, out, _ = self._svn(
            ["log", "-v", "--xml", "-r", rev_range],
            check=True
        )

        root = ET.fromstring(out)
        changes: List[RevisionChange] = []

        for entry in root.findall("logentry"):
            rid = entry.get("revision", "").strip()
            author = entry.findtext("author", "").strip()
            date = entry.findtext("date", "").strip()
            msg = entry.findtext("msg", "").strip()

            files = []
            paths = entry.find("paths")
            if paths is not None:
                for p in paths.findall("path"):
                    act = p.attrib.get("action", "?")
                    text = (p.text or "").strip()
                    if text:
                        files.append(FileChange(path=text, action=act))

            changes.append(
                RevisionChange(
                    revision=rid,
                    author=author,
                    date=date,
                    message=msg,
                    files=files,
                )
            )

        return changes

    # ------------------------------------------------------------------
    # 给单个文件生成 diff
    # ------------------------------------------------------------------

    def get_diff(
        self,
        revision: str,
        file_path: Optional[str] = None,
        max_lines: int = 200
    ) -> str:
        """
        获取某 revision 的 diff（可限制最大行数）。
        """
        args = ["diff", "-c", revision]
        if file_path:
            args.append(file_path)

        code, out, _ = self._svn(args, check=True)

        lines = out.splitlines()
        if len(lines) > max_lines:
            part = lines[:max_lines]
            part.append(
                f"...(剩余 {len(lines) - max_lines} 行已截断)"
            )
            return "\n".join(part)

        return out

    # ------------------------------------------------------------------
    # 按时间区间获取 external 的变更（统一以主库的时间为准）
    # ------------------------------------------------------------------

    def get_external_revision_list_by_time(
        self,
        t_start: Optional[str],
        t_end: str
    ) -> List[RevisionChange]:
        """
        根据时间区间获取 external 仓库的变更。

        时间格式示例：
            2025-12-10T08:23:11.123456Z
            2025-12-10T08:23:11Z
            2025-12-10

        注意：SVN 自动识别 {时间} 的写法。
        """

        if t_start:
            rev_range = f"{{{t_start}}}:{{{t_end}}}"
        else:
            rev_range = f"{{{t_end}}}"

        code, out, _ = self._svn(
            ["log", "-v", "--xml", "-r", rev_range],
            check=False
        )

        root = ET.fromstring(out or "<log/>")
        changes: List[RevisionChange] = []

        for entry in root.findall("logentry"):
            rid = entry.get("revision", "").strip()
            author = entry.findtext("author", "").strip()
            date = entry.findtext("date", "").strip()
            msg = entry.findtext("msg", "").strip()

            files = []
            paths = entry.find("paths")
            if paths is not None:
                for p in paths.findall("path"):
                    act = p.attrib.get("action", "?")
                    text = (p.text or "").strip()
                    if text:
                        files.append(FileChange(path=text, action=act))

            changes.append(
                RevisionChange(
                    revision=rid,
                    author=author,
                    date=date,
                    message=msg,
                    files=files,
                )
            )

        return changes

    # ------------------------------------------------------------------
    # 主函数：按时间区间收集变更（主库 + external）
    # ------------------------------------------------------------------

    def collect_change_summary(
        self,
        start_time: Optional[str],
        end_time: Optional[str],
        include_diff: bool = False,
        max_diff_lines: int = 200,
        include_externals: bool = True,
    ):
        """
        收集从 start_time → end_time 的所有变更。

        若 start_time 为空，则自动使用：
            上一次主库更新前的版本时间（before_update_rev）

        若 end_time 为空，则使用当前时间（UTC）。

        返回结构：
        {
            "main":   [RevisionChange, ...],
            "ext": {
                ext_url: [RevisionChange, ...]
            }
        }
        """
        import datetime

        # 自动推断起始时间
        if start_time is None:
            if not self.before_update_rev:
                raise VCSException("before_update_rev 未设置")
            start_time = self.get_rev_time(self.before_update_rev)

        # 自动推断终止时间
        if end_time is None:
            end_time = datetime.datetime.utcnow().isoformat() + "Z"

        logger.info("变更区间: %s -> %s", start_time, end_time)

        summary = {
            "main": [],
            "ext": {}
        }

        # ------------------------------
        # 主库变更（按时间区间，而不是按 revision）
        # ------------------------------
        summary["main"] = self.get_external_revision_list_by_time(
            start_time,
            end_time
        )

        # 生成 diff
        if include_diff:
            for rev in summary["main"]:
                for f in rev.files:
                    f.diff = self.get_diff(
                        rev.revision,
                        f.path,
                        max_lines=max_diff_lines
                    )

        # ------------------------------
        # external 变更
        # ------------------------------
        if include_externals:
            for e in self.get_all_externals():
                ext_ops = SvnOps(e)
                ext_url = ext_ops.get_current_url()

                ex_list = ext_ops.get_external_revision_list_by_time(
                    start_time, end_time
                )

                # 填入 diff
                if include_diff:
                    for rev in ex_list:
                        for f in rev.files:
                            f.diff = ext_ops.get_diff(
                                rev.revision,
                                f.path,
                                max_lines=max_diff_lines,
                            )

                summary["ext"][ext_url] = ex_list

        return summary

    # ------------------------------------------------------------------
    # 基于 update_to() 前后的版本号，生成 UpdateResult
    # ------------------------------------------------------------------

    def collect_update_result(
        self,
        include_diff: bool = False,
        max_diff_lines: int = 200,
        include_externals: bool = True
    ) -> UpdateResult:
        """
        在 update_to() 执行之后调用。

        根据 before_update_rev 和 after_update_rev 的时间，
        自动收集本次构建的所有变更（主仓库 + external）。

        返回 UpdateResult，用于构建记录、IC 推送等。
        """

        if not self.before_update_rev or not self.after_update_rev:
            raise VCSException("update_to() 未执行，无法生成更新结果")

        t_start = self.get_rev_time(self.before_update_rev)
        t_end = self.get_rev_time(self.after_update_rev)

        summary = self.collect_change_summary(
            start_time=t_start,
            end_time=t_end,
            include_diff=include_diff,
            max_diff_lines=max_diff_lines,
            include_externals=include_externals
        )

        all_changes: List[RevisionChange] = []

        # 主库变更
        for rev in summary["main"]:
            all_changes.append(rev)

        # external 变更
        for _, lst in summary["ext"].items():
            all_changes.extend(lst)

        # 按 revision 排序（非完美，但可用）
        def _key(c: RevisionChange):
            try:
                return int(c.revision)
            except ValueError:
                return 0

        all_changes.sort(key=_key)

        return UpdateResult(
            from_rev=self.before_update_rev,
            to_rev=self.after_update_rev,
            revision_changes=all_changes
        )
