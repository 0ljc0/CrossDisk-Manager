# CrossDisk Manager

面向 Windows 10/11 x64 的 Python + PySide6 跨分区文件管理器。目前完成任务 01～03：环境、中文三栏界面和真实磁盘/分区元数据清单。

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
- 配置字段：`theme`（system/light/dark）、`language`（目前仅 zh_CN）、窗口宽高、`show_hidden_files`、`read_only`（必须为 true）。主题与隐藏文件可在“视图”菜单切换，正常关闭时保存。
- 配置损坏或不安全时明确报错并停止启动，保留原配置。修复配置或备份后移走配置文件可恢复默认值。
- 异常日志只记录异常类型，不记录异常消息、文件内容和用户路径。

## 功能支持

| 功能 | 状态 |
|---|---|
| 中文三栏界面、退出、窗口大小与主题保存 | 已实现 |
| 模拟分区、目录导航、属性、当前目录名称筛选 | 已实现，仅内存演示 |
| 用户配置、轮转日志、未处理异常提示 | 已实现 |
| 磁盘、分区、Windows 卷元数据识别 | 已实现，后台只读查询 |
| 真实文件浏览、预览与复制 | 后续任务 |
| Windows 文件写入 | 后续任务，当前未实现 |
| ext4 访问 | 尚未接入；写入保持禁用 |

应用不打开原始磁盘设备句柄；任务 03 通过 Windows Storage 查询元数据，不挂载分区、不分配盘符、不更改隐藏/离线标志、不读写原始扇区。pytsk3 延至任务 05。详细进度见 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 任务 03 磁盘清单

默认启动时在后台调用固定的 Windows PowerShell `Get-Disk`、`Get-Partition`、`Get-Volume` 查询，解析 JSON 并在左侧按物理磁盘分组。点击磁盘或分区，在右侧查看型号、容量、大小、偏移、GUID、隐藏状态、盘符、卷标及文件系统等信息；右侧属性可滚动、复制，长 GUID 自动换行。树节点省略的文字可悬停查看。

刷新/F5 重新扫描，旧清单立即失效。超时、权限不足、PowerShell 缺失或格式错误会明确报错，可刷新重试；程序不会自动请求管理员权限。本机普通用户令牌已验证可以扫描。查询超时为 30 秒；扫描期间关闭窗口会等待查询结束或超时后退出，界面仍可响应。

所有真实分区仅展示元数据，文件浏览尚未实现；地址和文件搜索入口在此模式不可操作。EFI、MSR、Recovery 依据 GPT Type GUID 分类，隐藏/系统分区优先保护；Linux 数据类型不代表已确认 ext4。

磁盘标识优先使用 GPT GUID，其次设备 UniqueId；分区标识结合磁盘身份、Partition GUID、偏移、大小、类型和文件系统，不依赖编号/盘符。没有稳定磁盘身份时使用仅本次扫描有效的标识并明确标记，重插或刷新后需要重新选择，不应持久复用操作目标。

实现参考：[Get-Partition](https://learn.microsoft.com/en-us/powershell/module/storage/get-partition)、[GPT 分区类型](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ns-winioctl-partition_information_gpt)。本机核对记录见 [docs/TASK03_VALIDATION.md](docs/TASK03_VALIDATION.md)。

生成真实清单截图（只读查询，配置使用临时目录）：

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_inventory_ui
```

## 任务 02 界面演示

使用 `.\.venv\Scripts\python.exe -m app.main --demo` 启动纯模拟模式，不执行真实磁盘扫描。

左侧选择 C:、D:、Ubuntu、EFI、Recovery、MSR 或权限/未知卷演示项；双击中间的文件夹进入，使用后退、前进、向上、刷新操作。地址格式为 `mock-c:/用户文档`，回车跳转；搜索框仅筛选当前内存列表。选择文件显示模拟属性，尚无文件内容预览。

分区“可读写”表示模拟卷能力；应用全局只读仍开启，新建、重命名、删除、保存全部禁用，悬停或右侧属性可查看原因。受保护分区只展示模拟元数据，不请求管理员权限。

界面使用 QTreeView/QTableView 和独立模型；文件列表数据协议位于 `app/core/browser.py`，模拟实现为 `MockBrowserSource`，真实清单适配器 `InventoryBrowserSource` 明确不提供文件浏览。`MainWindow` 原有参数保持兼容，新增可选 `inventory_service` 注入后台扫描；主入口默认注入服务，`--demo` 使用模拟数据。

可执行 `.\.venv\Scripts\python.exe -m scripts.capture_mock_ui` 生成布局截图到 `docs/screenshots`。脚本只使用临时应用配置；窗口实际尺寸可能受当前显示器工作区限制，输出会列出请求尺寸、实际像素及 DPI 比例，截图不等同于多种物理显示器验收。
