# core/build_context.py
import os
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional


@dataclass
class BuildContext:
    """
    极简构建上下文：用于构建日志、IC 推送、构建产物等。
    """

    # Jenkins 环境
    workspace: str = ""
    work_root: str = ""
    job_url: str = ""
    build_user: str = ""         # 构建触发者（BUILD_USER）
    build_user_id: str = ""      # 构建触发者 ID
    build_url: str = ""          # 构建页面 URL
    build_number: str = ""       # 构建号（BUILD_NUMBER）
    node_name: str = ""          # 构建节点
    buid_note: str = ""        # 构建原因（可能为空）

    # 业务参数
    build_tag: str = ""          # 构建标签：trunk / mt8 / release 等
    at_user: str = ""            # 构建失败要通知谁
    error: str = ""              # 构建失败错误信息（第一行）

    # 构建工具
    unity_path: str = ""      # Unity 安装路径
    msbuild_path: str = ""    # MSBuild 安装路径
    file_server_root: str = ""  # 文件服务器根路径
    iggchat_token: str = ""  # 文件服务器根路径

    # 构建时间
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    # -------------------------
    # 控制台链接（失败跳用）
    # -------------------------
    def console_text_url(self) -> str:
        if not self.build_url:
            return ""
        # Jenkins 统一格式：<build_url>/consoleText
        return f"{self.build_url.rstrip('/')}/consoleText"

    # -------------------------
    # 构建耗时
    # -------------------------
    def duration_seconds(self) -> Optional[int]:
        if not self.end_time:
            return None
        return int((self.end_time - self.start_time).total_seconds())

    def duration_human(self) -> str:
        sec = self.duration_seconds()
        if sec is None:
            return "进行中"

        m, s = divmod(sec, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}小时{m}分{s}秒"
        elif m > 0:
            return f"{m}分{s}秒"
        return f"{s}秒"


# -------------------------
# 全局唯一实例
# -------------------------
GLOBAL_BUILD_CONTEXT = BuildContext()


# -------------------------
# 从 Jenkins 环境变量初始化
# -------------------------
def init_from_env(*, overwrite_existing: bool = True) -> BuildContext:
    ctx = GLOBAL_BUILD_CONTEXT

    def set_env(attr: str, key: str):
        val = os.getenv(key)
        if val is None:
            return
        if overwrite_existing or not getattr(ctx, attr):
            setattr(ctx, attr, val)

    set_env("workspace", "WORKSPACE")
    set_env("job_url", "JOB_URL")
    set_env("build_user", "BUILD_USER")
    set_env("build_user_id", "BUILD_USER_ID")
    set_env("build_url", "BUILD_URL")
    set_env("build_number", "BUILD_NUMBER")
    set_env("node_name", "NODE_NAME")
    set_env("unity_path", "UNITY_PATH")
    set_env("msbuild_path", "MSBUILD_PATH")
    set_env("iggchat_token", "IGGCHAT_TOKEN")
    set_env("file_server_root", "FILE_SERVER_ROOT")
    set_env("buid_note", "BUILD_NOTE")
    ctx.work_root = os.path.join(ctx.workspace, "work")
    return ctx


# -------------------------
# 设置 build_tag（构建阶段）
# -------------------------
def set_build_tag(tag: str):
    GLOBAL_BUILD_CONTEXT.build_tag = tag


# -------------------------
# 设置 at_user / error 等动态信息
# -------------------------
def set_build_context(
    *,
    at_user: Optional[str] = None,
    error: Optional[str] = None,
) -> BuildContext:
    ctx = GLOBAL_BUILD_CONTEXT

    if at_user is not None:
        ctx.at_user = at_user

    if error is not None:
        ctx.error = error.strip().split("\n")[0]  # 只保留第一行

    return ctx


# -------------------------
# 记录构建结束时间
# -------------------------
def mark_build_end():
    GLOBAL_BUILD_CONTEXT.end_time = datetime.now()


# -------------------------
# 序列化输出
# -------------------------
def to_dict() -> dict:
    ctx = GLOBAL_BUILD_CONTEXT
    d = asdict(ctx)

    d["start_time"] = ctx.start_time.strftime("%Y-%m-%d %H:%M:%S")
    d["end_time"] = ctx.end_time.strftime(
        "%Y-%m-%d %H:%M:%S") if ctx.end_time else None
    d["duration_seconds"] = ctx.duration_seconds()
    d["duration_human"] = ctx.duration_human()
    d["console_text_url"] = ctx.console_text_url()

    return d


def dump_to_json(path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(to_dict(), f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------
# 构建成功摘要（使用 build_url）
# ---------------------------------------------------------
def build_success_summary(*, extra: str) -> str:
    ctx = GLOBAL_BUILD_CONTEXT
    start = ctx.start_time.strftime("%Y-%m-%d %H:%M:%S")

    return (
        f"[status=success "
        f"build_user={ctx.build_user or '-'} "
        f"start={start} "
        f"extra={extra} "
        f"tag={ctx.build_tag or '-'} "
        f"url={ctx.build_url or '-'}]"
    )


# ---------------------------------------------------------
# 构建失败摘要（使用 consoleText）
# ---------------------------------------------------------
def build_failure_summary() -> str:
    ctx = GLOBAL_BUILD_CONTEXT
    start = ctx.start_time.strftime("%Y-%m-%d %H:%M:%S")
    err = ctx.error or "-"

    return (
        f"[status=failure "
        f"build_user={ctx.build_user or '-'} "
        f"start={start} "
        f"tag={ctx.build_tag or '-'} "
        f"at_user={ctx.at_user or '-'} "
        f"url={ctx.console_text_url() or '-'} "
        f"error={err}]"
    )
