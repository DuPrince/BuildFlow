# BuildFlow

BuildFlow 是一套轻量级的构建管线工具，用来把「拉代码 → 编译 → 发布 → 通知」串成一条可配置、可复用的流水线。

它的设计目标是：

- **统一入口**：Jenkins、本地命令行都只调用一个 `build_cmd.py`
- **统一参数协议**：用 `env_arg / vcs_arg / build_arg / notify_arg` 四类参数描述一次构建
- **可扩展**：先支持 Git + C# 编译 + IC 通知，后续可以逐步挂上 SVN、Unity 打包、FTP/OSS 上传等能力

---

## 核心能力

- **多源代码仓支持（VCS 层）**
  - 当前聚焦 Git（clone/pull/reset/子模块同步）
  - 提供本地 vs 远端的提交差异信息（作者列表 / 提交列表）

- **可配置的构建流程（Build 层）**
  - 支持 C# Solution 编译（MSBuild 或 `dotnet build`）
  - 支持配置输出目录、构建配置（Debug/Release）

- **统一的构建结果通知（Notify 层）**
  - 集成 IC 推送（构建成功/失败）
  - 自动附带：触发信息、分支、提交摘要、作者列表、关键错误日志

- **与 CI 系统友好集成**
  - 入口统一为 `python build_cmd.py ...`
  - 参数通过一行字符串传入，易于在 Jenkins 等系统中配置

---

## 目录结构

> 以下为推荐结构，实际仓库可按需调整。

```text
BuildFlow/
  README.md

  build_cmd.py                # 唯一入口：本地 / Jenkins 都只调用它

  core/
    __init__.py

    env_args.py               # env_arg 解析与封装
    vcs_args.py               # vcs_arg 解析与封装（Git / SVN）
    build_args.py             # build_arg 解析与封装
    notify_args.py            # notify_arg 解析与封装

    vcs/
      __init__.py
      git_helper.py           # Git 同步、diff、作者信息等
      # svn_helper.py         # 未来扩展

    build/
      __init__.py
      cs_build.py             # C# Solution 编译逻辑
      # unity_build.py        # 未来扩展

    notify/
      __init__.py
      ic_client.py            # IC 推送实现

    utils/
      __init__.py
      log.py                  # 日志封装
      path.py                 # 路径工具

  config/
    projects/
      example_project.json    # 项目示例配置

  jenkins/
    Jenkinsfile.sample        # Jenkins 样例
    build_job_example.bat     # Windows Job 样例
