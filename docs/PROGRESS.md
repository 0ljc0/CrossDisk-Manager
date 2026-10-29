# 项目进度

更新日期：2026-10-29。

## 任务 01：已验收并提交

用户于 2026-10-29 确认继续任务 02；任务 01 基线提交：`3636640`。

- 创建 `.venv`，使用本机 Python 3.12.8；固定 PySide6 6.10.0、pytest 8.4.2。
- 建立 app/core、ui、backends、services、jobs 包及 tests。
- 实现中文最小主窗口、正常退出和窗口尺寸保存，统一入口 `python -m app.main`。
- 配置覆盖主题、中文语言、窗口大小、隐藏文件选项；只读默认开启且禁止关闭。
- 实现用户目录日志、轮转、去敏异常类型记录和未处理异常提示。
- 补充 README、依赖清单、pyproject.toml 和 .gitignore。
- 没有实现磁盘扫描、文件浏览或文件系统写入后端，没有访问真实磁盘设备或 Ubuntu 分区。

## 任务 01 实际验证（历史记录）

- Windows 本机 Python 3.12.8 虚拟环境创建成功。
- `python -m pip install -r requirements.txt` 安装成功；首次沙箱网络失败，获准联网重试成功。
- `.\.venv\Scripts\python.exe -m pytest -q`：**10 passed in 1.11s**。
- 测试覆盖配置默认值与往返、无效/不安全配置拒绝、损坏配置保留、用户目录定位、日志落盘、Qt 窗口显示/关闭与尺寸保存。
- 子进程运行真实 app.main 模块和 Qt 事件循环，由测试计时器关闭窗口，退出码 0；配置、启动及退出日志均验证成功。未使用 offscreen 平台。
- `.\.venv\Scripts\python.exe -m pip check`：**No broken requirements found.**
- 测试配置和日志限定于 pytest 临时目录，没有对真实分区做读写测试。

## 当前已知问题与限制

- `py` 启动器仅注册 Python 3.14；已发现未注册的 Python 3.12.8，README 提供其创建虚拟环境的方法。
- 已接入 Windows 原生只读文件浏览；Ubuntu 文件读取尚未接入，尚未安装 pytsk3。
- 尚未在独立 Windows 10/其他机器及独立 2K/4K 显示器上验收。
- 任务 01～03 已提交；任务 04 按“先验收，再提交”约定保留工作区供用户验收。
- 沙箱执行器中途出现 setup refresh 错误；测试改在获准的宿主环境执行。Git 所有者为沙箱账号，宿主只读检查需使用单次 `-c safe.directory=D:/crossdisk_manager`，无需改全局 Git 配置。

## 任务 02：已验收并提交

用户于 2026-10-29 明确验收成功并要求开始任务 03；提交：`9aa6057`。

- 中文菜单、三行工具栏、左分区树、中间文件表、右侧属性区和底部状态栏；支持拖动分栏和长文件名省略/悬停显示。
- 展示 C:、D:、Ubuntu、EFI、Recovery、MSR，以及权限不足和不可识别演示卷，状态及禁用原因可见。
- 全部数据来自 `MockBrowserSource` 内存样本，不调用磁盘或提权接口。可读写代表模拟卷能力，应用全局只读约束仍生效，所有写入操作禁用。
- 实现双击进入文件夹、后退/前进/向上/刷新、模拟地址回车跳转、当前目录名称筛选、隐藏文件显示和属性展示。
- 覆盖加载中、空目录、无匹配结果、受保护、权限不足、不可浏览、路径不存在等状态；快速切换时忽略过期加载回调。
- 主题菜单提供系统/浅色/深色，主题、窗口大小、隐藏文件设置在正常关闭时保存并可恢复。
- 新增 `app/core/browser.py` 数据类和查询协议、`app/backends/mock_browser.py` 内存实现、`app/ui/browser_models.py` Qt 模型；`MainWindow` 原三个参数兼容，增加可选 source 参数。
- 更新 README；新增 `tests/test_mock_ui.py`、`scripts/capture_mock_ui.py` 与 `docs/screenshots/task02-*.png`。

### 任务 02 实际验证

- `.\.venv\Scripts\python.exe -m pytest -q`：**23 passed in 5.74s**（含任务 01 回归和 app.main 子进程启动）。
- 新增测试覆盖三栏布局、分区选择、目录进入、历史导航、向上、地址输入、刷新、空目录、名称筛选、隐藏文件、8 类分区的写入禁用原因、快速切换、主题/尺寸恢复及文件属性。
- 执行 `.\.venv\Scripts\python.exe -m scripts.capture_mock_ui` 成功生成四张原生 Qt 窗口截图；检查默认浅色和宽窗口深色画面，修正属性标题留白问题后重跑测试并更新截图。
- 当前 Windows 缩放为 150%（DPR=1.5）：默认逻辑 1000×680 得到 1500×1020 截图；请求更大窗口时被工作区限制。1080p/2K/4K 文件名表示请求档位，实际截图分别为 2880×1571、3840×1571、4484×1571，不能当作独立物理分辨率验收。
- `git diff --check` 无空白错误，仅提示 Git 默认的 LF/CRLF 换行转换。
- 没有访问 PhysicalDrive、真实 ext4、EFI/Recovery 或分区表；本阶段没有文件写入后端。

## 下一步

等待用户验收任务 04；验收后提交 Git，再由用户决定是否执行 `docs/tasks/05_Ubuntu_ext4只读接入.md`。任务 05～12 均未开始。

## 任务 03：已验收并提交

用户确认“下一个任务”后提交为 `4330ce8`，开始任务 04。

- 新增 `core/inventory.py` 值对象、`services/disk_inventory.py` 固定 Storage 查询与 JSON 解析、`jobs/inventory_worker.py` 后台线程、`backends/inventory_browser.py` 只展示元数据的适配器。
- 扩展分区树按真实磁盘分组；展示编号、型号、容量、分区类别和状态，属性区提供大小、偏移、GUID、隐藏标志、盘符、卷标与文件系统等字段。
- 稳定身份不依赖磁盘/分区编号；缺失身份降为当次扫描标识，冲突/不一致快照明确失败。刷新立即清空旧设备清单，避免继续使用过期目标。
- 查询为固定编码脚本，不接受用户参数插值；UTF-8 JSON 兼容单对象、数组和 null。失败/超时明确展示，可重试，不自动提权。
- 真实分区全为元数据模式，不提供文件浏览或写入。默认启动真实清单，`--demo` 保留任务 02；构造函数旧参数保持兼容，新增可选 inventory_service。
- 属性区改为只读文本视图，支持长 GUID 换行与滚动；保留原 text/setText 接口。
- 新增扫描与 UI 测试、真实截图脚本、截图、`TASK03_VALIDATION.md`，更新 README。无新依赖。

### 任务 03 实际结果

- 最终测试：**45 passed in 7.86s**；`pip check` 无依赖冲突；`git diff --check` 无空白错误。
- 实机普通用户令牌（Administrator=False）扫描成功：YMTC 953.87 GiB，1 个磁盘、6 个分区、3 个卷。
- 使用独立 `Get-Partition | Format-Table ...` 逐项核对编号、大小和偏移，全部一致；详细字节数据见 `TASK03_VALIDATION.md`。
- 约 150 GiB 的分区 6 被识别为 Linux 数据类型，文件系统保持“未识别”；IsHidden=True，界面按受保护展示。
- 后台真实清单界面启动、分区属性展示、截图及关闭均完成；未调用原始磁盘写 API，未进行真实文件浏览。
- 查询期间关闭窗口需等待查询结束/30 秒超时，期间界面保持响应。物理热插拔、多物理盘和独立 Windows 10 环境仍未实测；错误场景采用模拟验证。

## 任务 04：已实现并通过测试，待用户验收

- 新增 `app/backends/windows_native.py`，实现 list_dir、stat、open_read、get_capabilities，只暴露只读能力与 rb 流；没有文件写入接口。
- 将已验证、普通且非隐藏的 Windows 数据卷绑定到 Volume GUID 根；支持盘符输入、已验证卷 GUID 输入和用户明确指定的普通 UNC 共享。保护/未知/身份不可靠分区仍为元数据模式。
- 新增 `app/jobs/native_query.py`、`directory_worker.py`：每批最多 200 项、非递归、子进程执行、15 秒超时、取消旧查询、忽略过期结果；点击“加载下一批”继续。F5 刷新当前目录，“重扫磁盘”更新设备清单。
- 路径校验阻止遍历、设备名、备用流；使用只读属性句柄固定目录组件，不跟随符号链接/junction/重解析点。中文、空格、隐藏属性及超长路径已验证。
- FileEntry 新增带默认值的链接、读写提示与属性错误字段，PartitionInfo 新增默认卷路径；原构造参数兼容。目录页为 DirectoryPage，GUI 不在主线程访问文件系统。
- 更新文件表头、文件/目录/链接图标、属性及权限说明，保留模拟模式。未做文件内容预览、复制、写入或 ext4 接入。
- 新增 `tests/test_windows_native.py`、`test_native_ui.py`、`scripts/capture_native_ui.py`、实机截图与 `TASK04_VALIDATION.md`；更新 README，无新依赖。

### 任务 04 实际结果与问题

- 最终全套测试 **76 passed, 1 skipped in 16.08s**；pip check 无依赖问题。跳过的是需要符号链接创建权限的临时循环链接测试（WinError 1314）；没有提权。
- 实机 C:\Users 普通模式 3 项、显示隐藏文件后 8 项；D:\crossdisk_manager 可进入 app 并返回；现有 junction 明确禁止进入；受限目录正确显示“访问被拒绝”。
- 真实独占文件锁测试发现 WinError 32 属于 PermissionError 子类，已调整判断顺序，准确显示“文件被占用”。
- 超长路径、实际子进程分页/导航/取消与 UI 响应验证通过；截图已检查，所有写入按钮继续禁用。
- 真实 UNC 共享、超大实机目录及独立平台未实测；共享/超时错误用模拟验证。保守禁止跟随全部重解析点；后续批次会重新枚举并跳过已加载部分，目录变化时需刷新，详情见 TASK04_VALIDATION.md。
- 未执行任何格式化、分区表修改、盘符分配、ACL 绕过、原始磁盘写入或 Ubuntu 文件读取/写入。
