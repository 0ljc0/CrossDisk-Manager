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
- 已完成模拟三栏界面与隐藏文件显示；尚未安装 pytsk3 或接入真实磁盘。
- 尚未在独立 Windows 10/其他机器及独立 2K/4K 显示器上验收。
- 任务 01 已提交；任务 02 按“先验收，再提交”约定保留工作区供用户验收。
- 沙箱执行器中途出现 setup refresh 错误；测试改在获准的宿主环境执行。Git 所有者为沙箱账号，宿主只读检查需使用单次 `-c safe.directory=D:/crossdisk_manager`，无需改全局 Git 配置。

## 任务 02：已实现并通过测试，待用户验收

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

等待用户验收任务 02；验收后提交 Git，再由用户决定是否执行 `docs/tasks/03_磁盘及分区识别.md`。任务 03～12 均未开始。
