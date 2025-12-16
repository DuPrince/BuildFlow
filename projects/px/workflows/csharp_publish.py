# -*- coding: utf-8 -*-
import os
import json
import shutil
import logging
from typing import Dict, List, Optional
from pathlib import Path

from core.build_context import (
    init_from_env,
    set_build_context,
    mark_build_end,
    build_failure_summary,
    build_success_summary,
)

from modules.vcs.git_ops import sync_repo_with_info
from modules.vcs.svn_ops import SvnOps  # 你已有的大版本 svn_ops
from modules.notify.ic_util import send_to_group, send_to_user
from modules.build.csharp_builder import build_csharp  # 按你现有文件名调整 import

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    pass


def _load_json(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_mkdir(path: str):
    os.makedirs(path, exist_ok=True)


def svn_has_changes(repo_path: str) -> bool:
    ops = SvnOps(repo_path)
    code, out, _ = ops._svn(["status"], check=False)
    if code != 0:
        # status 失败也算异常
        raise WorkflowError(f"svn status failed: {repo_path}")
    for line in (out or "").splitlines():
        if not line.strip():
            continue
        # 常见：? 未加入 / M 修改 / A 新增 / D 删除 / ! 丢失
        if line[0] in ("?", "M", "A", "D", "R", "C", "!", "~"):
            return True
    return False


def svn_auto_add_remove(repo_path: str):
    ops = SvnOps(repo_path)
    code, out, _ = ops._svn(["status"], check=False)
    if code != 0:
        raise WorkflowError(f"svn status failed: {repo_path}")

    for line in (out or "").splitlines():
        if not line.strip():
            continue
        flag = line[0]
        path = line[1:].strip()
        if not path:
            continue

        if flag == "?":
            ops._svn(["add", "--force", path], check=False)
        elif flag == "!":
            ops._svn(["delete", "--force", path], check=False)


def sparse_update(workspace: str, profile: Dict):
    """
    你说的加强版 sparse_update：
    - 仓库不存在：sparse checkout（你已有 ensure_sparse_workspace 会做）
    - 仓库存在：update + 按 paths 做 depth 展开
    """
    ops = SvnOps(workspace)
    ops.ensure_sparse_workspace(profile)

    projects = profile.get("projects") or {}
    for name, proj in projects.items():
        root_path = proj.get("root_path")
        if not root_path:
            continue
        project_path = os.path.join(workspace, root_path)
        pop = SvnOps(project_path)

        # 先 update 根
        pop._svn(["update"], check=True)

        # 再按规则展开
        paths = proj.get("paths") or []
        if not paths:
            continue

        def _depth(p: str) -> int:
            return p.strip("/").count("/")

        sorted_paths = sorted(paths, key=lambda x: _depth(x["path"]))
        for item in sorted_paths:
            rel = item["path"].strip("/")
            depth = item.get("depth", "infinity")
            pop._svn(["update", rel, "--depth", depth], check=True)


def sparse_commit(workspace: str, profile: Dict, message: str) -> List[str]:
    """
    你说的加强版 sparse_commit：只传 profile + message
    返回：实际提交的 project 列表（root_path）
    """
    committed = []
    projects = profile.get("projects") or {}
    for name, proj in projects.items():
        root_path = proj.get("root_path")
        if not root_path:
            continue
        project_path = os.path.join(workspace, root_path)

        if not svn_has_changes(project_path):
            continue

        svn_auto_add_remove(project_path)

        pop = SvnOps(project_path)
        pop._svn(["commit", "-m", message], check=True)
        committed.append(root_path)

    return committed


def notify_failure(ctx, *, stage: str, err: Exception, git_info: Optional[Dict] = None):
    set_build_context(error=str(err))
    extra = f"[stage={stage}]\n{str(err)}"
    if git_info:
        extra += "\n\n" + format_git_block(git_info, max_commits=20)

    msg = build_failure_summary(extra=extra)

    if ctx.iggchat_token and ctx.iggchat_room_id:
        send_to_group(ctx.iggchat_token, msg, ctx.iggchat_room_id,
                      title="Build Failed", at_user=ctx.at_user)
    # 如你还想 DM 个人，可在 BuildContext 里加 notify_user，然后这里 send_to_user


def notify_success(ctx, *, text: str):
    msg = build_success_summary(extra=text)
    if ctx.iggchat_token and ctx.iggchat_room_id:
        send_to_group(ctx.iggchat_token, msg,
                      ctx.iggchat_room_id, title="Build Success")


def run_csharp_publish(
    *,
    git_repo: str,
    git_branch: str,
    git_dir: str,
    sln_path: str,
    configuration: str,
    force: bool = False,
    ssh_key: Optional[str] = None,
):
    ctx = init_from_env()
    try:
        # 1) Git sync
        git_info = sync_repo_with_info(
            url=git_repo,
            dest=git_dir,
            branch=git_branch,
            ssh_key=ssh_key,
            recursive=True,
            lfs=True,
        )

        if (not force) and (not git_info.get("changed", False)):
            notify_success(ctx, text="Git no changes -> skip build/commit")
            return

        # 2) SVN sparse update
        here = Path(__file__).resolve()
        px_root = here.parents[1]
        svn_profile_json = os.path.join(
            px_root, "configs", "svn_sparse_profile.json")
        profile = _load_json(svn_profile_json)
        sparse_update(ctx.work_root, profile)

        # 4) C# build verify
        if not ctx.msbuild_path:
            raise WorkflowError("MSBUILD_PATH 未设置（建议 Jenkins 全局环境变量提供）")

        br = build_csharp(
            ctx.msbuild_path,
            sln_path,
            configuration=configuration,
            restore=True,
            rebuild=True,
        )
        if not br.success:
            raise WorkflowError(
                f"C# build failed: code={br.returncode}\n{br.stderr}")

        # 5) SVN commit（svn 有变化才提交）
        commit_msg = (
            f"{format_git_block(git_info, max_commits=50)}\n"
            f"build_id: {ctx.build_id or ctx.build_number or '-'}\n"
            f"trigger_reason: {ctx.build_note or '-'}\n"
            f"jenkins_console: {ctx.console_text_url() or '-'}\n"
        )

        committed = sparse_commit(svn_workspace, profile, commit_msg)

        if committed:
            notify_success(ctx, text="SVN committed: " + ", ".join(committed))
        else:
            notify_success(ctx, text="SVN no changes -> skip commit")

    except Exception as e:
        logger.exception("workflow failed")
        notify_failure(ctx, stage="workflow", err=e,
                       git_info=locals().get("git_info"))
        raise
    finally:
        mark_build_end()
