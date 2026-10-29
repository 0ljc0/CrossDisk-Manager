# CrossDisk Manager

面向 Windows 10/11 x64 的 Python + PySide6 跨分区文件管理器。任务 01～04 已验收；任务 05 的 ext4 只读接入及镜像验证已实现，真实 Ubuntu 分区人工验收待完成。

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
| Windows 文件只读浏览与属性 | 已实现，按需分批加载 |
| 文件内容预览与复制 | 后续任务 |
| Windows 文件写入 | 后续任务，当前未实现 |
| ext4 访问 | 已实现只读后端，真实 pytsk3 镜像测试通过；实盘待人工验收 |

默认扫描通过 Windows Storage 查询元数据。用户明确选择 Linux 候选后，独立子进程才尝试以 pytsk3 只读打开当前设备，并重新验证身份与格式；绝不写原始扇区、不挂载系统盘、不分配盘符、不更改隐藏/离线标志或分区表。pytsk3 固定为本机验证版本 20260715。详细进度见 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 任务 03 磁盘清单

默认启动时在后台调用固定的 Windows PowerShell `Get-Disk`、`Get-Partition`、`Get-Volume` 查询，解析 JSON 并在左侧按物理磁盘分组。点击磁盘或分区，在右侧查看型号、容量、大小、偏移、GUID、隐藏状态、盘符、卷标及文件系统等信息；右侧属性可滚动、复制，长 GUID 自动换行。树节点省略的文字可悬停查看。

“重扫磁盘”重新扫描，旧清单立即失效；刷新/F5 仅刷新当前目录，未选目录时执行磁盘扫描。超时、权限不足、PowerShell 缺失或格式错误会明确报错，可重试；程序不会自动请求管理员权限。本机普通用户令牌已验证可以扫描。磁盘查询超时为 30 秒；扫描期间关闭窗口会等待查询结束或超时后退出，界面仍可响应。

普通、已识别且稳定身份可用的 Windows 数据卷支持只读浏览。EFI、MSR、Recovery 和系统保护分区继续只显示元数据。已确认 GPT 身份的 Linux 数据类型可作为只读探测候选，隐藏标志不授予 Windows 文件访问或任何写入能力；Linux 数据类型不代表已确认 ext4。

磁盘标识优先使用 GPT GUID，其次设备 UniqueId；分区标识结合磁盘身份、Partition GUID、偏移、大小、类型和文件系统，不依赖编号/盘符。没有稳定磁盘身份时使用仅本次扫描有效的标识并明确标记，重插或刷新后需要重新选择，不应持久复用操作目标。

实现参考：[Get-Partition](https://learn.microsoft.com/en-us/powershell/module/storage/get-partition)、[GPT 分区类型](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ns-winioctl-partition_information_gpt)。本机核对记录见 [docs/TASK03_VALIDATION.md](docs/TASK03_VALIDATION.md)。

生成真实清单截图（只读查询，配置使用临时目录）：

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_inventory_ui
```

## 任务 04 Windows 只读浏览

扫描完成后选择 C:/D: 等普通 Windows 分区，或在地址栏输入 `C:\Users`、`D:\crossdisk_manager` 后回车。双击目录进入，使用后退/前进/向上导航。文件仅显示属性，尚不打开预览或编辑器。

- 本地目录通过扫描到的 Volume GUID 根绑定，地址栏盘符只是当前清单的显示/路由信息；已验证卷的完整 `\\?\Volume{GUID}\...` 地址同样可用，无盘符时也可通过树选择有已识别卷路径的普通数据分区。
- 可显式输入普通 UNC 路径（例如 `\\server\share\资料`）；共享受 Windows 登录凭据和 ACL 约束，不存储密码或自动提权。管理共享、原始设备和 GLOBALROOT 路径被拒绝。真实网络共享尚未实测。
- Windows 隐藏属性由“视图 → 显示隐藏文件”控制，点号开头的文件并不自动视为 Windows 隐藏文件。
- 每批最多 200 个可见项，点击“加载下一批”继续；不会递归扫描。搜索框仅筛选已经加载的项，不搜索磁盘。目录发生变化时可能需要刷新重新分页，不承诺目录快照一致性。
- 每次目录查询在可取消子进程中执行，15 秒超时；切换目录会取消旧请求，超时或网络阻塞不阻塞 GUI。磁盘扫描仍使用独立线程。
- 所有符号链接、junction、挂载点及其他重解析点只展示自身属性，不跟随，以防止越界、循环或意外读取受保护卷；因此 OneDrive 等重解析点内容也可能受限。
- 超长路径使用 Windows 扩展路径；拒绝 `..`、备用数据流、保留设备名等。目录组件由只读属性句柄固定，不允许在本次读取期间重命名替换。文件内容读取 API 仅暴露 `rb` 流。
- 文件表提供通用文件/目录/链接图标、大小、修改时间、读写属性提示。权限提示并非 ACL 授权判断，实际读取仍可能被 Windows 拒绝；应用始终禁用写入。

后端接口为 `NativeWindowsBackend.list_dir/stat/open_read/get_capabilities`；分页结果为 `DirectoryPage`。`FileEntry` 新增带默认值的链接/权限/错误字段，`PartitionInfo` 新增默认空值的卷路径，原构造参数保持兼容。GUI 通过后台分页加载；旧 `list_directory` 同步适配接口仅返回首批，不能用于完整目录遍历或 GUI 主线程。

只读实现参考：[Python scandir](https://docs.python.org/3.12/library/os.html#os.scandir)、[Windows CreateFile](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)。本机结果见 [docs/TASK04_VALIDATION.md](docs/TASK04_VALIDATION.md)。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_native_ui
```

此验收脚本按本机任务环境检查 `C:\Users`、D 盘当前项目、既有 junction 和受限目录；不会写入这些目录，应用配置放在临时目录。

## 任务 05 ext4 只读接入

已阅读原始 `D:\谷歌浏览器\read_ubuntu_partition6.py` 并保持其不变。新实现位于 `app/backends/ext4_readonly.py`，不固定物理磁盘号、分区号、用户目录或容量。

- 扫描仅将具有稳定磁盘/GPT 分区身份的 Linux 数据分区标记为“待验证”。明确单击后，子进程重新查询 Storage，对照磁盘 GUID/UniqueId、分区 GUID、大小、偏移、卷标、文件系统及系统标志。
- 打开当前 `PhysicalDrive` 后，再校验 GPT 头与分区表 CRC、磁盘 GUID、分区 GUID/类型及字节范围，避免查询后编号复用。随后检查 ext4 超级块、状态、特征、UUID 和卷标，最后才构造 `FS_Info(..., offset=...)`。
- 不处理 LUKS、LVM、未知格式、需日志恢复、不干净状态、加密、inline、casefold、bigalloc 等不兼容情况，不尝试恢复或解锁。只读不代表支持全部 ext4 特性。
- 所有 pytsk3 文件系统读取受选定分区范围约束。`list_dir/stat/open_read/close` 支持分批目录、流式文件读取和资源释放；能力始终 `read=True, write=False`，源后端没有 write/rename/remove。
- 符号链接仅展示本身属性，不跟随；非法 UTF-8 名称显示替代字符并禁止进入。未分配条目不当作正常文件，损坏 inode/短读明确报错。Unix 权限位仅作提示，不等同于授权或后端写入能力。
- 探测成功后树显示“只读 ext4”；该分区选中时地址栏可输入 `/home`，或使用 `分区稳定标识:/home`。同一扫描会话保留 UUID/卷标/特征指纹，变化时拒绝继续读取，需要用户重新扫描选择。
- ext4 查询同样在可取消子进程中执行，45 秒超时覆盖 Storage 身份复核；取消会回收本次查询进程树。Windows 目录仍为 15 秒，磁盘扫描仍为 30 秒。

GUI 不自动提权。普通账户无法读取原始设备时会明确提示独立管理员读取进程方案；本阶段没有把管理员读取结果通过 IPC 回传普通 GUI 的代理服务。需要权限时，仅由用户明确打开管理员 PowerShell 运行下述独立工具，不以管理员身份启动整个 GUI。原始读取可能失败或格式不兼容，不能自动降级为盲读。

纯镜像验收（无需管理员，不访问任何真实分区；使用项目内合成镜像生成器）：

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_ext4_image_ui
```

真实分区只作人工验收。先列举当次稳定 ID，再替换下述占位值：

```powershell
.\.venv\Scripts\python.exe -m scripts.ext4_readonly --list-candidates
.\.venv\Scripts\python.exe -m scripts.ext4_readonly --partition-id "替换为当次候选ID" --action ls --path /
.\.venv\Scripts\python.exe -m scripts.ext4_readonly --partition-id "替换为当次候选ID" --action ls --path /home
.\.venv\Scripts\python.exe -m scripts.ext4_readonly --partition-id "替换为当次候选ID" --action sample --path "/home/替换为用户名/替换为普通样本文本.txt"
```

`sample` 仅将选定普通文件流式导出到新建 Windows 临时文件（`xb`），核对字节数和 SHA-256 后自动清理；不输出文件内容、不覆盖已有文件。这是任务 05 的验收工具，GUI 的导出/复制队列仍未开发。

`DirectoryPage` 增加可选 source_info，能力模型末尾增加默认 read 字段，`PartitionInfo` 末尾增加默认系统/启动标志，原参数位置保持兼容。目录 worker 增加可选 backend_spec；既有 Windows 查询方式不变。

实现参考：[pytsk 项目与读取接口](https://github.com/py4n6/pytsk)、[Linux ext4 超级块规范](https://www.kernel.org/doc/html/latest/filesystems/ext4/super.html)。详细证据、限制与待验收项见 [docs/TASK05_VALIDATION.md](docs/TASK05_VALIDATION.md)。

## 任务 02 界面演示

使用 `.\.venv\Scripts\python.exe -m app.main --demo` 启动纯模拟模式，不执行真实磁盘扫描。

左侧选择 C:、D:、Ubuntu、EFI、Recovery、MSR 或权限/未知卷演示项；双击中间的文件夹进入，使用后退、前进、向上、刷新操作。地址格式为 `mock-c:/用户文档`，回车跳转；搜索框仅筛选当前内存列表。选择文件显示模拟属性，尚无文件内容预览。

分区“可读写”表示模拟卷能力；应用全局只读仍开启，新建、重命名、删除、保存全部禁用，悬停或右侧属性可查看原因。受保护分区只展示模拟元数据，不请求管理员权限。

界面使用 QTreeView/QTableView 和独立模型；文件列表数据模型位于 `app/core/browser.py`，模拟实现为 `MockBrowserSource`，真实清单适配器 `InventoryBrowserSource` 提供已验证根映射。`MainWindow` 原有参数保持兼容，`inventory_service` 注入后台扫描；主入口默认注入服务，`--demo` 使用模拟数据。

可执行 `.\.venv\Scripts\python.exe -m scripts.capture_mock_ui` 生成布局截图到 `docs/screenshots`。脚本只使用临时应用配置；窗口实际尺寸可能受当前显示器工作区限制，输出会列出请求尺寸、实际像素及 DPI 比例，截图不等同于多种物理显示器验收。
