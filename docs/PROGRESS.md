# 项目进度

更新日期：2026-10-29。

## 任务 01：已实现并通过自动化测试，待用户验收

- 创建 `.venv`，使用本机 Python 3.12.8；固定 PySide6 6.10.0、pytest 8.4.2。
- 建立 app/core、ui、backends、services、jobs 包及 tests。
- 实现中文最小主窗口、正常退出和窗口尺寸保存，统一入口 `python -m app.main`。
- 配置覆盖主题、中文语言、窗口大小、隐藏文件选项；只读默认开启且禁止关闭。
- 实现用户目录日志、轮转、去敏异常类型记录和未处理异常提示。
- 补充 README、依赖清单、pyproject.toml 和 .gitignore。
- 没有实现磁盘扫描、文件浏览或文件系统写入后端，没有访问真实磁盘设备或 Ubuntu 分区。

## 实际验证

- Windows 本机 Python 3.12.8 虚拟环境创建成功。
- `python -m pip install -r requirements.txt` 安装成功；首次沙箱网络失败，获准联网重试成功。
- `.\.venv\Scripts\python.exe -m pytest -q`：**10 passed in 1.11s**。
- 测试覆盖配置默认值与往返、无效/不安全配置拒绝、损坏配置保留、用户目录定位、日志落盘、Qt 窗口显示/关闭与尺寸保存。
- 子进程运行真实 app.main 模块和 Qt 事件循环，由测试计时器关闭窗口，退出码 0；配置、启动及退出日志均验证成功。未使用 offscreen 平台。
- `.\.venv\Scripts\python.exe -m pip check`：**No broken requirements found.**
- 测试配置和日志限定于 pytest 临时目录，没有对真实分区做读写测试。

## 已知问题与限制

- `py` 启动器仅注册 Python 3.14；已发现未注册的 Python 3.12.8，README 提供其创建虚拟环境的方法。
- 只有最小窗口；隐藏文件配置尚无可作用的浏览界面；尚未安装 pytsk3。
- 自动化验证窗口可显示和退出，人工视觉验收仍待用户完成；尚未在独立 Windows 10/其他机器验收。
- 已初始化 Git。按任务包“先验收，再提交”的约定，当前未创建提交，待用户验收后提交。
- 沙箱执行器中途出现 setup refresh 错误；测试改在获准的宿主环境执行。Git 所有者为沙箱账号，宿主只读检查需使用单次 `-c safe.directory=D:/crossdisk_manager`，无需改全局 Git 配置。

## 下一步

等待用户验收任务 01；验收后提交 Git，再由用户决定是否执行 `docs/tasks/02_图形界面框架.md`。任务 02～12 均未开始。
