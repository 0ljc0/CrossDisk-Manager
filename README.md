# CrossDisk Manager

面向 Windows 10/11 x64 的 Python + PySide6 跨分区文件管理器。已实现任务 01～11 的环境、只读源后端、统一导航、安全预览、搜索、复制导出、Windows 受控写入及 ext4 写入准入接口；ext4 写入保持安全禁用。真实 Ubuntu 分区人工验收仍待完成，当前 ext4 证据来自真实 pytsk3 镜像测试。

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
| 统一路径、面包屑、跨后端历史与能力策略 | 已实现；保护分类优先，写入始终禁用 |
| 文本/代码/图片只读预览 | 已实现，有读取、像素及展示上限 |
| 当前目录即时筛选、跨分区元数据搜索 | 已实现，手动启动即时扫描，无持久索引 |
| 文件/目录复制与导出队列 | 已实现 Windows → Windows、ext4 → Windows，仅新建、不覆盖 |
| Windows 文件编辑/新建/重命名/移动/删除 | 已实现，独立窗口内明确配置的数据目录，保护卷禁用 |
| ext4 访问 | 已实现只读后端，真实 pytsk3 镜像测试通过；实盘待人工验收 |
| ext4 写入适配 | 协议及明确拒绝后端已实现；无已验证驱动，写入禁用 |

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

扫描完成后选择 C:/D: 等普通 Windows 分区，或在地址栏输入 `C:\Users`、`D:\crossdisk_manager` 后回车。双击目录进入，使用后退/前进/向上导航；选中文件后在右侧显示属性与只读预览。

- 本地目录通过扫描到的 Volume GUID 根绑定，地址栏盘符只是当前清单的显示/路由信息；已验证卷的完整 `\\?\Volume{GUID}\...` 地址同样可用，无盘符时也可通过树选择有已识别卷路径的普通数据分区。
- 可显式输入普通 UNC 路径（例如 `\\server\share\资料`）；共享受 Windows 登录凭据和 ACL 约束，不存储密码或自动提权。管理共享、原始设备和 GLOBALROOT 路径被拒绝。真实网络共享尚未实测。
- Windows 隐藏属性由“视图 → 显示隐藏文件”控制，点号开头的文件并不自动视为 Windows 隐藏文件。
- 每批最多 200 个可见项，点击“加载下一批”继续；目录浏览不会递归扫描。工具栏筛选框仅筛选已经加载的项；递归搜索使用独立的“跨分区搜索”窗口。目录发生变化时可能需要刷新重新分页，不承诺目录快照一致性。
- 每次目录查询在可取消子进程中执行，15 秒超时；切换目录会取消旧请求，超时或网络阻塞不阻塞 GUI。磁盘扫描仍使用独立线程。
- 所有符号链接、junction、挂载点及其他重解析点只展示自身属性，不跟随，以防止越界、循环或意外读取受保护卷；因此 OneDrive 等重解析点内容也可能受限。
- 超长路径使用 Windows 扩展路径；拒绝 `..`、备用数据流、保留设备名等。目录组件由只读属性句柄固定，不允许在本次读取期间重命名替换。文件内容读取 API 仅暴露 `rb` 流。
- 文件表提供通用文件/目录/链接图标、大小、修改时间、读写属性提示。权限提示并非 ACL 授权判断，实际读取仍可能被 Windows 拒绝；应用始终禁用写入。

后端接口为 `NativeWindowsBackend.list_dir/stat/open_read/get_capabilities`；分页结果为 `DirectoryPage`。GUI 通过后台分页加载；旧 `list_directory` 同步适配接口仅返回首批，并经过统一后端工厂与策略检查，不能用于完整目录遍历或 GUI 主线程。任务 06 的字段兼容性说明见下文。

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

## 任务 06 统一路径、导航与权限

- `FileSystemBackend` 定义统一的 `list_dir/stat/open_read/get_capabilities` 只读协议；Windows 与 ext4 均实现该协议，不定义写接口。后台通过 `backend_access` 创建后端，执行操作前再次检查分类及实际后端能力。
- 内部使用 `VirtualPath(partition_id, path)`，路径为相对分区根的 POSIX 字符串，保留大小写。规范化重复分隔符和 `.`，处理分区内 `..`，越过根则拒绝；不会把 Ubuntu `/home` 自动解释成 Windows 盘符路径。后端继续执行各自的名称与链接边界校验，不跟随链接。
- 地址栏、后退/前进/向上和可点击面包屑共用 VirtualPath。面包屑根按钮保留分区身份，切换到其他后端后再返回，会恢复原分区与目录。宽度不足时可以横向滚动面包屑和文件表。
- `CapabilityPolicy` 优先检查 GPT 类型及系统/隐藏保护，再查询后端功能。EFI、MSR、Recovery 分别给出说明；未知或没有后端的分区仅显示元数据。错误的 browsable 标志、用户昵称或声明 write=True 都不能绕过策略；所有写操作仍禁用，右键菜单没有写入口。
- 文件表统一显示名称、大小、类型、修改时间、权限提示、访问状态和后端来源。缺失的大小、时间、类型、链接或权限信息显示“未知”；“属性已读取”只表示元数据读取成功，不代表有效 ACL 授权或内容一定可读取。
- 导航开始时立即使旧请求失效并清空旧列表；旧成功与旧失败回调均不能覆盖新目录。地址、策略与后端错误都在中央消息页和状态栏展示，不记录文件内容或路径到错误日志。

兼容性：旧 `Location` 导入名仍为 VirtualPath 别名，支持原来的位置参数、`relative_path=` 构造与 `.relative_path` 访问。新代码使用 `.path/.parent/.child/.breadcrumbs()`；`asdict(VirtualPath)` 输出 partition_id/path，不能继续假设序列化键为 relative_path。现有 worker 仍显式传递旧 relative_path JSON 键，已修复全部现有调用者。`FileEntry` 的字段位置保留，权限/链接改为 bool/None 三态，默认未知的大小为 None、时间为空；表格和属性区已适配。新增 category/backend_name 及 backend_source/access_status 字段均在原字段后。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_unified_navigation
```

上述脚本在同一窗口验证真实 `C:\Users` 与合成 ext4 镜像 `/home` 的切换、历史与面包屑，并生成任务 06 截图。真实 Ubuntu 分区不参与自动化读取。详细结果见 [docs/TASK06_VALIDATION.md](docs/TASK06_VALIDATION.md)。

## 任务 07 安全文本、代码与图片预览

选中普通文件即可在右侧预览；双击文件仍只在应用内预览。右侧属性和预览之间的分隔条可拖动，文本可滚动和复制，始终只读，没有编辑或执行按钮。

- 文本类型：txt、md、py、json、yaml/yml、log、csv。按纯文本展示，Markdown/HTML 不执行或加载链接，CSV 不计算公式，Python 不运行。
- 自动检测 UTF-8、UTF-8 BOM、UTF-16 BOM，以及可可靠识别的无 BOM UTF-16；编码不明确时提示手选 UTF-8、UTF-16 LE/BE、GB18030 或 CP1252。手选只改变本次预览解码，不转换或保存源文件。
- 已知可执行/压缩/PDF/图片头不会当文本输出，解码失败或二进制控制字符会明确提示。未知扩展名仅显示属性与不支持提示，不调用外部程序或系统文件关联。
- 默认仅读取文本前 2 MiB（另最多 1 字节作截断探测），默认最多展示 25 万字符/1 万行。“查看更多”每次增加 2 MiB 读取预算，同时提高展示预算；最大 8 MiB、100 万字符/4 万行。截断显示“预览已截断”，达到安全上限后按钮禁用，绝不自动读完整大文件。显示时统一换行符，不修改源文件。
- 图片类型：png、jpg/jpeg、bmp、webp，实际依赖 Qt 解码插件；文件头与内容不匹配会拒绝。数据上限 16 MiB，像素上限 1600 万、单边不超过 16384；Qt 单次图片分配上限固定 64 MiB。
- 原图解码及最大 1024×768 缩略图在子进程中完成，仅返回内存 PNG（最多 4 MiB）。主进程再次校验缩略图头与尺寸；不在源目录生成图片/文本缓存。读进程使用 `-B` 和 PYTHONDONTWRITEBYTECODE 禁止生成源文件字节码缓存。
- 切换文件、进入目录、重扫磁盘、出现导航错误或关闭窗口都会取消旧预览；预览使用独立请求编号，旧成功/失败消息不能覆盖新文件。Windows 请求 15 秒、ext4 请求 45 秒超时，保留独立进程方案与真实分区权限限制。
- 预览前重新获取文件属性和读取能力，沿用分类保护及链接禁止跟随。展示来源分区、相对路径、大小、修改时间与只读状态；元数据不等同于实际授权，读取被拒绝或损坏文件只显示错误，不退出应用。

`open_backend` 新增可选 operation 参数（默认 list_dir），分别检查 list_dir/stat/open_read 的实际能力。新增 PreviewResult、预览服务、PreviewWorker 与 PreviewPanel；既有目录 worker 构造参数不变，新增 task=preview 的内部 JSON 消息，目录返回结构兼容。无新增依赖。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_preview_ui
```

脚本只读检查 D 盘项目代码、README、已有 PNG 及 ext4 合成镜像文本，比较源文件 SHA-256/修改时间并生成四张项目验收截图。详细证据见 [docs/TASK07_VALIDATION.md](docs/TASK07_VALIDATION.md)。图片限制参考 [Qt 6.10 QImageReader 文档](https://doc.qt.io/qtforpython-6.10/PySide6/QtGui/QImageReader.html)。

## 任务 08 搜索与筛选

工具栏可按名称/路径、扩展名和类型即时筛选当前目录已加载的条目。点击“跨分区搜索”（Ctrl+Shift+F），选择当前目录递归、当前分区或全部可搜索来源，填写条件后明确点击“开始搜索”；不会自动扫描整个磁盘。

- 搜索只遍历名称、路径、类型、大小、修改日期等元数据，不读取文件正文。名称含 `*`、`?`、`[` 时按通配符匹配，否则按子串匹配；扩展名用逗号或分号分隔，支持 `.py`、`*.md`、`.tar.gz`。路径条件按子串匹配。
- 支持文件/目录/链接类型、最小/最大字节数、包含首尾日期的 `YYYY-MM-DD` 修改日期范围。未知属性不能满足对应的限制条件。默认 Windows 不区分大小写、ext4 区分大小写，也可手动指定。
- 全部来源只包含策略允许的已映射 Windows 卷、明确登记的普通 UNC 来源及本次会话已完成只读验证的 ext4。EFI、MSR、Recovery、受保护/未知/无后端分区及未验证 Linux 候选被排除，并显示原因。实际目录权限仍由后端检查，识别成功不代表整个分区可读。
- 显示已检查目录/条目、命中数、来源进度、错误目录/条目及跳过链接、深度和重复目录统计。错误明细最多保留前 100 项；权限错误、超时或预算停止明确显示部分结果，不显示为全部完成。取消保留已返回的结果；主窗口关闭也会取消搜索。
- 双击结果按分区稳定身份和相对路径定位：文件/链接定位父目录，普通目录定位自身，不自动预览文件内容。重扫磁盘会取消搜索并使旧结果失效；来源消失或策略变化会拒绝定位。
- 不跟随符号链接、junction 或其他重解析点；检测重复目录，限制深度与分页偏移。默认最多深度 32、5000 个结果、20 万条目、2 万目录、300 秒；配置模型上限分别为 64、1 万、50 万、5 万、600 秒，界面提供深度和结果数设置。各来源顺序扫描并共享预算，较早来源可能耗尽预算，后续来源因此未完成。
- 搜索在独立子进程中执行，可取消并回收本次进程树；另有 60 秒无消息看门狗及总时间保护。待处理/已访问路径约束为 16 MiB，结果载荷预算 32 MiB，消息队列有界；这些限制触发时保留部分结果并说明原因。
- 本阶段采用即时扫描，未实现可选 SQLite 索引，不持久保存搜索结果，不生成源目录缓存；没有后台磁盘监控或文件上传。既有配置、日志仍位于 Windows 用户配置目录。

新增 SearchQuery/SearchLimits/SearchResult/SearchStats、搜索服务、独立 NDJSON 后台协议、SearchWorker、SearchDialog 与 FileFilterProxy；既有后端和目录/预览 worker 的公共调用方式保持兼容，MainWindow.filter_entries 入口不变。无新增依赖。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_search_ui
```

验收脚本仅搜索 C 盘新建临时目录、D 盘项目 app 和合成 ext4 镜像 `/home`，不是全盘验收，也不读取真实 Ubuntu 分区。生成三张截图并验证来源归属、结果定位及镜像散列不变。完整证据与限制见 [docs/TASK08_VALIDATION.md](docs/TASK08_VALIDATION.md)。

## 任务 09 安全复制与导出队列

选中普通文件或目录，点击“复制/导出到 Windows…”，选择现有 Windows 数据目录、冲突策略并确认来源和目标。可多次添加任务，队列串行执行，主窗口仍可浏览。目标只接受本次清单允许的本地 Volume GUID 映射；不接受 UNC、ext4、原始设备、卷根、重解析目录或系统关键目录。源仍为只读，编辑、保存、重命名和删除保持禁用。

- 默认跳过同名文件，目录冲突跳过整个目录；可选择冲突时报错，始终没有覆盖选项。ext4 仅开放已验证来源 `/home/` 下的用户数据；Windows 系统关键路径不参与复制，符号链接与未知属性条目跳过。
- 1 MiB 流式块写入目标同目录独占 `.crossdisk-随机标识.partial`，核对源属性、总字节数及落盘 SHA-256，刷新后通过 Windows 不覆盖 rename 发布。目标竞争出现时失败，不替换既有文件。每个文件开始前检查空间，写入时实际 ACL 和剩余空间仍可能导致失败。
- 目标全部祖先目录持有禁止共享删除的属性句柄，拒绝重解析点。取消/失败仅删除本次创建且未发布的临时文件；保留已完成文件和新建目录。失败停止当前任务，队列可继续；不会回滚已经发布的文件。
- 后台线程提供状态、完成/失败/跳过数、已传输/已发现字节量。总量随目录遍历增长，不是预先完整统计；暂停/取消在读取块之间检查，阻塞中的设备调用完成前不能立即响应。关闭窗口请求取消并等待清理，不强杀写入线程。
- 重试最后任务从头重新读取，已完成文件按冲突策略处理；同一会话仅复用该任务记录且文件身份一致的新建目录，其他既有目录不合并。不提供断点续传；队列不持久化。
- 最多 10 万条目、深度 32（模型最大 64）、一小时协作时间预算；不跟随目录链接，分页检查必须前进。文件时间戳/属性暂不保留，界面明确提示。无新增依赖，既有后端公共接口不变；目标保护复用 Windows 后端内部目录句柄机制。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_copy_ui
```

脚本通过真实 Windows Volume GUID 将测试文件和合成 ext4 `/home/demo` 导出到项目内临时目录，核对字节、哈希及源镜像不变，然后清理测试目录；不读取真实 Ubuntu。真实 Ubuntu → `D:\CrossDisk_TestExport` 仍待人工验收，不能以镜像证据替代。详见 [docs/TASK09_VALIDATION.md](docs/TASK09_VALIDATION.md)。

## 任务 10 Windows 受控写入与编辑

选择普通 Windows 数据卷后，点击“配置 Windows 写入目录…”，明确选择同卷现有数据目录并确认。独立写入窗口中的路径相对于该目录；作用域只保留本次窗口会话，不持久授权。主浏览器仍为只读，其旧写入按钮不启用；写入使用独立窗口的操作按钮。现有配置 `read_only=true` 继续保护默认浏览后端，不代表禁止用户明确授权的独立写入上下文。

- 支持新建空文件/目录、同目录重命名、同卷移动、UTF-8 文本打开与保存、回收站删除及二次确认永久删除。新建、重命名与移动不覆盖既有目标；跨卷移动使用任务 09 复制流程，本窗口不自动复制删除。
- 写入仅允许在线、非只读、稳定身份的普通本地数据卷；Windows 启动/系统卷、EFI/MSR/Recovery、隐藏/未知/离线/锁定卷和 ext4 禁用。配置目录及祖先不能是链接或重解析点，卷根、作用域自身及系统关键目录不可操作。实际 ACL 拒绝时停止，不提权或更改权限。
- 每个操作在后台线程重新扫描 Storage，核对完整分区/磁盘快照与 Volume GUID，再由 CapabilityPolicy 和后端验证。目录祖先持有禁止删除共享的属性句柄；目标名称必须符合 Windows 规则，不接受越界、备用流或设备名。
- 文本仅支持不超过 2 MiB 的 UTF-8，保存统一为 UTF-8 无 BOM。保存独占创建同目录临时文件，刷新落盘，最后重新核对原内容 SHA-256；最终检查及替换期间拒绝普通外部写句柄，以 Windows ReplaceFileW 同卷原子替换并生成唯一 `.crossdisk-随机标识.bak` 原文件备份。失败不主动删除备份或原文件，编辑内容保留；文件冲突要求重新打开。不支持无限文本或其他编码编辑，请使用只读预览。
- 默认删除通过系统 Shell 回收站，保留系统确认；无法回收时 Shell 应显示永久删除警告，不做静默永久删除降级。独立“永久删除”按钮必须经应用两次确认并明确不可恢复。仅支持普通文件/空目录，不递归删除。应用不提供“撤销”按钮；可通过系统回收站或人工核对 .bak 恢复。
- 操作期间关闭窗口需等待完成；未保存文本关闭或切换前询问放弃。没有强杀写入线程、批量递归删除或自动备份清理。备份需用户自行管理；并发名称替换不具有跨进程事务隔离保证，重要文件应先停止外部修改并核对备份。

```powershell
.\.venv\Scripts\python.exe -m scripts.capture_write_ui
```

脚本默认在 D 盘项目内新临时目录执行真实身份复核及新建、保存、备份、重命名、移动、永久删除；可加 `--test-root D:\CrossDisk_TestWrite` 在任务指定目录内创建独立临时子目录验收，已实际执行通过。仅清理本次临时子目录，不修改既有文件，不触及系统目录或 Ubuntu。系统回收站交互与恢复仍待人工完成。详见 [docs/TASK10_VALIDATION.md](docs/TASK10_VALIDATION.md)。

接口兼容：NativeWindowsBackend 增加可选仅关键字 `write_context`，原调用方式及默认只读能力保持不变；新增六个写操作没有上下文时直接拒绝。CapabilityPolicy 新增 require_windows_write，不改变既有 evaluate 的只读结果。ext4 后端仍没有写接口。无新依赖、没有实施任务 11。

## 任务 11 ext4 写入准入评估

当前构建明确显示“只读：未接入已验证的受控写入驱动；ext4 写入禁用”。工具栏“ext4 写入准入说明”展示证据缺口；该入口只显示说明，没有安装、挂载或开启写入的按钮。Linux 候选的只读格式验证与写入准入互相独立，验证过 ext4 UUID 不会获得写权限。

已调查 Paragon Linux File Systems for Windows、Ext4Fsd、原 Ext2Fsd/Ext3Fsd 与 WSL2 方案的官方资料。共用 Windows 系统盘不能通过 `wsl --mount` 附加；不把系统盘离线，不用 pytsk3 或原始扇区修改代替文件系统写驱动。候选声明、许可证、兼容性与特征矩阵及证据缺口见 [可行性报告](docs/EXT4_WRITE_FEASIBILITY.md)，不代表候选已在本机通过验证。

新增 `Ext4WritableAdapter` 协议、`Ext4WriteCapabilities`、`Ext4AdmissionStatus` 和 `UnsupportedWriteError`。`get_ext4_write_backend()` 当前始终返回 `UnsupportedWriteBackend`，直接调用创建、保存、重命名、移动、删除或 flush 都抛出明确异常，不执行 I/O。没有配置、环境变量或自称 write=True 的解锁途径；不改动 pytsk3 只读层，Windows 独立写入路径不受此协议影响，无新依赖。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ext4_write_admission.py -q
.\.venv\Scripts\python.exe -m scripts.capture_ext4_admission_ui
```

脚本仅使用合成普通镜像验证只读浏览、按钮禁用与镜像 SHA-256 不变，不读取真实 Ubuntu。未安装或调用任何实际写驱动，未执行 Linux 重挂载、离线完整性检查或断电恢复测试；未来须使用用户另行提供的可丢弃镜像/独立测试盘，并满足全部准入条件才可评估接入。本任务以安全禁用方案交付，未开始任务 12。验证记录见 [TASK11_VALIDATION.md](docs/TASK11_VALIDATION.md)。

## 任务 02 界面演示

使用 `.\.venv\Scripts\python.exe -m app.main --demo` 启动纯模拟模式，不执行真实磁盘扫描。

左侧选择 C:、D:、Ubuntu、EFI、Recovery、MSR 或权限/未知卷演示项；双击中间的文件夹进入，使用后退、前进、向上、刷新操作。地址格式为 `mock-c:/用户文档`，回车跳转；搜索框仅筛选当前内存列表。选择文件显示模拟属性，尚无文件内容预览。

分区“可读写”表示模拟卷能力；应用全局只读仍开启，新建、重命名、删除、保存全部禁用，悬停或右侧属性可查看原因。受保护分区只展示模拟元数据，不请求管理员权限。

界面使用 QTreeView/QTableView 和独立模型；文件列表数据模型位于 `app/core/browser.py`，模拟实现为 `MockBrowserSource`，真实清单适配器 `InventoryBrowserSource` 提供已验证根映射。`MainWindow` 原有参数保持兼容，`inventory_service` 注入后台扫描；主入口默认注入服务，`--demo` 使用模拟数据。

可执行 `.\.venv\Scripts\python.exe -m scripts.capture_mock_ui` 生成布局截图到 `docs/screenshots`。脚本只使用临时应用配置；窗口实际尺寸可能受当前显示器工作区限制，输出会列出请求尺寸、实际像素及 DPI 比例，截图不等同于多种物理显示器验收。
