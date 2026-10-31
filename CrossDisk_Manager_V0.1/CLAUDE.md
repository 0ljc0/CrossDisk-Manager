# CrossDisk Manager 开发代理通用约束（CLAUDE.md）

适用于 Claude Code；对 Codex 同样适用。必须先读真实项目，再读当前任务文档和上一份真实交接报告。

## 用户环境

- 项目实际目录：`D:\crossdisk_manager\CrossDisk_Manager_V0.1`（名称仍为 V0.1，但代码已升级至 V0.3.1；不要为改版本号随意移动目录）。
- 现有文件：`main.py`、`storage_scan.py`、`volume_links.py`、`fs_adapters.py`、`preview_utils.py`、`diagnose_links.py`、`test_storage_scan.py`、`test_links_adapters.py`、`test_preview_utils.py`、`requirements.txt`、`.venv/`。
- 已知硬件：磁盘 0 的分区 3 为 Windows C:、分区 4 为 D:、分区 6 为 Ubuntu ext4；Paragon 能将 Ubuntu 挂载到 E:，但盘符可能变化。
- 目前的 `ReadOnlyMountedAdapter` 明确拒绝写入，不能因为 Paragon 已安装就开放任何写操作。
- 仅 V0.1/V0.2.1 的部分实机功能和 Windows 读取 Ubuntu 测试文件 SHA-256 一致得到用户验证；V0.3.1 的完整 Windows GUI 回归尚需现场验收。


## 工作范围

- 所有工作在现有 Windows 项目内增量执行；保护已经通过的功能。一次只执行用户指定的一个 task。
- 需求文档是计划，不代表实现；每次都先检查真实源码、已有接口、测试结果。
- 不得假设 Windows 上的 E: 永远是 Ubuntu，也不得因为软件系统盘符/卷标显示 EXT4 就认定当前可写。
- Git 不得清理、覆盖用户未提交修改，不得覆盖已有 `.venv`。
- 代码、用户提示、报告保持中文；函数和数据模型可以使用清晰英文标识。
- Linux ext4：现阶段通过 Paragon 挂载路径访问；`pytsk3` 为只读备用。禁止引入未经验证的裸扇区写入。
- Windows 与 Linux 文本换行、编码、大小写、Linux UID/GID、符号链接都属于验收范围。
- Windows 读写只能在用户授权的正常数据目录下生效，系统特殊分区始终受保护。

## 全任务统一安全要求

1. 严禁执行 `format`、`diskpart clean`、`Clear-Disk`、`Remove-Partition`、`Set-Partition`、`Set-Disk -IsOffline` 或任何修改分区表/EFI/Recovery/MSR 的命令；不直接开启 `\\.\PhysicalDrive0` 写句柄。
2. 默认禁止对 Ubuntu 分区 6 做任何文件创建、覆盖、删除、移动或属性修改；只有任务 08 在任务 07 实际通过、备份完成、明确授权且限定范围时才例外。
3. 对驱动、分区身份、权限或实际挂载模式存在疑问时，结果为 `UNKNOWN` 或 `READ_ONLY`，不推测具备写权限。
4. 除任务 05 在用户授权的 Windows 专用测试目录、任务 07 在独立可丢弃 ext4 测试介质、任务 08 在额外明确授权的 Ubuntu 专用测试目录外，真实磁盘只允许元数据查询和只读操作；自动化单元测试优先使用 `TemporaryDirectory` 或模拟适配器。
5. 不自动提升管理员权限；不能通过 `os.access`、磁盘类型、盘符、Windows 卷标志或人工关联推断 ext4 写入安全性。
6. 任何可能改变 Windows 文件的功能，必须在用户指定的测试目录中测试；禁止自动对真实个人文件进行 CRUD 测试。
7. 每次开发前检查 Git 状态并保留当前可用版本。若项目未初始化 Git，先征询用户或在项目目录内初始化；不得强制覆盖、重置或清理其未提交修改。


## 自动测试与现场验收

- 修改代码前后运行现有测试，新增测试只使用模拟/临时路径；禁止单元测试写入 Ubuntu E:。
- 单元测试通过不能自动代表真实 Paragon 驱动兼容或 Linux 回侧一致性通过。
- 如果缺少 PySide6/Windows API 环境，应写“本机待验收”，不得声称已在 Windows 实机运行。
- 每次生成 `docs/handoffs/NN_交接报告.md`，填写真实证据，不允许空白模板直接标 PASS。
- 若前一任务阻断，优先解决阻断；当 07/08 的实盘安全条件不满足时，产品必须以只读降级方案继续。

## 终止条件

遇到真实磁盘归属不明、用户授权缺失、数据备份缺失、ext4 特性兼容性无法确认、意外权限放开、测试崩溃或源数据可能损坏，立即停止相关写入并报告风险。不要自行尝试修复、格式化或改变驱动挂载选项。
