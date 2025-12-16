# -*- coding: utf-8 -*-
"""
git_ops.py

Git 工具链（终极版）
- 支持 SSH 私钥（方案 A）
- 支持 submodule + LFS
- 支持 update_repo_with_info：返回本次更新的详细提交信息
- 仅依赖 Python 标准库
- 适合 CI / 构建系统 / Unity 项目
"""

import os
import subprocess
import logging
from typing import List, Dict, Optional

# =========================================================
# logging
# =========================================================
logger = logging.getLogger(__name__)

# =========================================================
# exceptions
# =========================================================


class GitCommandError(Exception):
    pass


class GitError(Exception):
    pass

# =========================================================
# SSH key strategy (方案 A)
# =========================================================


def get_default_ssh_key() -> str:
    """
    默认 SSH key 策略：
    1) 环境变量 PXTA_SSH_KEY
    2) ~/.ssh/id_ed25519
    3) ~/.ssh/id_rsa
    """
    env_key = os.getenv("PXTA_SSH_KEY")
    if env_key and os.path.exists(env_key):
        return env_key

    for p in (
        os.path.expanduser("~/.ssh/id_ed25519"),
        os.path.expanduser("~/.ssh/id_rsa"),
    ):
        if os.path.exists(p):
            return p

    raise GitError("未找到可用的 SSH key")


def _build_ssh_env(ssh_key: Optional[str]) -> dict:
    key = ssh_key or get_default_ssh_key()
    if not os.path.exists(key):
        raise GitError(f"SSH key 不存在: {key}")

    env = os.environ.copy()
    null_dev = "NUL" if os.name == "nt" else "/dev/null"

    env["GIT_SSH_COMMAND"] = (
        f"ssh -i '{key}' "
        "-o StrictHostKeyChecking=no "
        f"-o UserKnownHostsFile={null_dev}"
    )
    return env

# =========================================================
# low level git runner
# =========================================================


def run_git(
    args: List[str],
    cwd: Optional[str] = None,
    ssh_key: Optional[str] = None,
) -> str:
    cmd = ["git"] + args
    logger.info(f"[git] {' '.join(cmd)} (cwd={cwd})")

    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=_build_ssh_env(ssh_key),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )

    if proc.returncode != 0:
        raise GitCommandError(proc.stderr.strip())

    return proc.stdout.strip()


def _ensure_repo(path: str):
    if not os.path.exists(os.path.join(path, ".git")):
        raise GitError(f"不是 Git 仓库: {path}")

# =========================================================
# basic ops
# =========================================================


def clone(url: str, dest: str, branch: str = None,
          recursive=True, lfs=True, ssh_key=None):
    args = ["clone", url, dest]
    if branch:
        args += ["-b", branch]
    if recursive:
        args.append("--recursive")

    run_git(args, ssh_key=ssh_key)

    if lfs:
        lfs_install(dest, ssh_key)
        lfs_pull(dest, ssh_key)


def fetch(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["fetch", "--all"], cwd=path, ssh_key=ssh_key)


def checkout(path: str, target: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["checkout", target], cwd=path, ssh_key=ssh_key)


def pull(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["pull"], cwd=path, ssh_key=ssh_key)

# =========================================================
# submodule
# =========================================================


def submodule_sync(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["submodule", "sync", "--recursive"], cwd=path, ssh_key=ssh_key)


def submodule_update(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["submodule", "update", "--init", "--recursive"],
            cwd=path, ssh_key=ssh_key)

# =========================================================
# LFS
# =========================================================


def lfs_install(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["lfs", "install"], cwd=path, ssh_key=ssh_key)


def lfs_pull(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["lfs", "fetch", "--all"], cwd=path, ssh_key=ssh_key)
    run_git(["lfs", "pull"], cwd=path, ssh_key=ssh_key)


def lfs_pull_all_submodules(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(
        ["submodule", "foreach", "--recursive", "git lfs pull"],
        cwd=path,
        ssh_key=ssh_key,
    )

# =========================================================
# reset / clean
# =========================================================


def reset_hard(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["reset", "--hard", "HEAD"], cwd=path, ssh_key=ssh_key)


def clean_untracked(path: str, ssh_key=None):
    _ensure_repo(path)
    run_git(["clean", "-fd"], cwd=path, ssh_key=ssh_key)


def reset_repo_and_submodules(path: str, ssh_key=None):
    reset_hard(path, ssh_key)
    clean_untracked(path, ssh_key)
    run_git(
        ["submodule", "foreach", "--recursive", "git reset --hard HEAD"],
        cwd=path,
        ssh_key=ssh_key,
    )
    run_git(
        ["submodule", "foreach", "--recursive", "git clean -fd"],
        cwd=path,
        ssh_key=ssh_key,
    )

# =========================================================
# commit / diff helpers
# =========================================================


def get_head(path: str) -> str:
    _ensure_repo(path)
    return run_git(["rev-parse", "HEAD"], cwd=path)


def get_commits_between(path: str, a: str, b: str) -> List[Dict]:
    """
    返回 a..b 之间的提交信息
    """
    if a == b:
        return []

    fmt = "%H|%an|%ae|%ad|%s"
    out = run_git(
        ["log", f"{a}..{b}", f"--pretty=format:{fmt}", "--date=iso"],
        cwd=path,
    )
    commits = []
    for line in out.splitlines():
        h, an, ae, ad, msg = line.split("|", 4)
        commits.append({
            "commit": h,
            "author": an,
            "email": ae,
            "date": ad,
            "message": msg,
        })
    return commits


def get_submodule_states(path: str) -> Dict[str, str]:
    """
    返回 {submodule_path: commit}
    """
    _ensure_repo(path)
    out = run_git(["submodule", "status", "--recursive"], cwd=path)
    result = {}
    for line in out.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            commit = parts[0].lstrip("+-")
            sub_path = parts[1]
            result[sub_path] = commit
    return result

# =========================================================
# update with info (核心)
# =========================================================


def update_repo(
    url: str,
    dest: str,
    branch: str = None,
    recursive=True,
    lfs=True,
    ssh_key=None,
    *,
    reset: bool = True,
    clean: bool = True,
) -> Dict:
    """
    更新仓库，并返回本次更新的详细信息：
    - 主仓库提交
    - submodule 提交

    参数说明：
    - reset=True  : 执行 git reset --hard（主仓库 + submodule）
    - clean=True  : 执行 git clean -fd（主仓库 + submodule）
    默认二者都 False（安全）
    """

    # ---------- before ----------
    main_before = get_head(dest) if os.path.exists(dest) else None
    subs_before = get_submodule_states(dest) if main_before else {}

    # ---------- update ----------
    if not os.path.exists(dest):
        clone(url, dest, branch, recursive, lfs, ssh_key)
    else:
        # ====== 破坏性操作（显式 opt-in） ======
        if reset:
            logger.warning("[git_ops] reset --hard（主仓库）")
            reset_hard(dest, ssh_key)

            if recursive:
                logger.warning("[git_ops] reset --hard（submodule）")
                run_git(
                    ["submodule", "foreach", "--recursive", "git reset --hard HEAD"],
                    cwd=dest,
                    ssh_key=ssh_key,
                )

        if clean:
            logger.warning("[git_ops] clean -fd（主仓库）")
            clean_untracked(dest, ssh_key)

            if recursive:
                logger.warning("[git_ops] clean -fd（submodule）")
                run_git(
                    ["submodule", "foreach", "--recursive", "git clean -fd"],
                    cwd=dest,
                    ssh_key=ssh_key,
                )

        # ====== 正常更新流程 ======
        if branch:
            checkout(dest, branch, ssh_key)

        fetch(dest, ssh_key)
        pull(dest, ssh_key)

        if recursive:
            submodule_sync(dest, ssh_key)
            submodule_update(dest, ssh_key)

        if lfs:
            lfs_install(dest, ssh_key)
            lfs_pull(dest, ssh_key)
            lfs_pull_all_submodules(dest, ssh_key)

    # ---------- after ----------
    main_after = get_head(dest)
    subs_after = get_submodule_states(dest)

    info = {
        "repo": {
            "path": dest,
            "from": main_before,
            "to": main_after,
            "commits": (
                get_commits_between(dest, main_before, main_after)
                if main_before else []
            ),
        },
        "submodules": [],
    }

    for sub_path, new_commit in subs_after.items():
        old_commit = subs_before.get(sub_path)
        if old_commit and old_commit != new_commit:
            full_path = os.path.join(dest, sub_path)
            info["submodules"].append({
                "path": sub_path,
                "from": old_commit,
                "to": new_commit,
                "commits": get_commits_between(
                    full_path, old_commit, new_commit
                ),
            })

    return info
