# CrossDisk Manager

面向 Windows 10/11 x64 的 Python + PySide6 跨分区文件管理器。目前仅完成任务 01：环境、配置、日志和最小中文窗口。

## 安装与运行

使用 Python 3.11 或 3.12，在普通 PowerShell 中进入项目根目录执行，无需管理员权限：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
.\.venv\Scripts\python.exe -m pytest -q
```

本机 Python 3.12 未注册到 `py` 启动器，可用以下命令替代第一行：

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv
```

必须从项目根目录启动；在其他工作目录使用前先 `Set-Location D:\crossdisk_manager`（按实际位置替换）。不要求激活虚拟环境。

## 配置与日志

- 配置：`%LOCALAPPDATA%\CrossDiskManager\config.json`，正常关闭窗口时保存大小。
- 日志：同目录下 `logs\app.log`，单文件约 1 MB，保留 3 份历史。
- 配置字段：`theme`（system/light/dark）、`language`（目前仅 zh_CN）、窗口宽高、`show_hidden_files`、`read_only`（必须为 true）。隐藏文件选项仅存储，尚无文件浏览功能。
- 配置损坏或不安全时明确报错并停止启动，保留原配置。修复配置或备份后移走配置文件可恢复默认值。
- 异常日志只记录异常类型，不记录异常消息、文件内容和用户路径。

## 功能支持

| 功能 | 状态 |
|---|---|
| 中文最小窗口、退出、窗口大小保存 | 已实现 |
| 用户配置、轮转日志、未处理异常提示 | 已实现 |
| 磁盘发现、文件浏览、预览与复制 | 后续任务 |
| Windows 文件写入 | 后续任务，当前未实现 |
| ext4 访问 | 尚未接入；写入保持禁用 |

本阶段仅写入应用自身配置和日志，不打开磁盘设备，不扫描分区。pytsk3 延至任务 05。详细进度见 [docs/PROGRESS.md](docs/PROGRESS.md)。
