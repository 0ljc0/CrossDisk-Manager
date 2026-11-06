# CrossDisk Manager

**中文** | [English](README.en.md)

面向 Windows 10/11 x64 的跨分区文件管理器，使用 Python、PySide6 和 pytsk3。支持 Windows 文件浏览、预览、搜索、复制，以及明确授权目录内的受控写入；Ubuntu ext4 当前只读。

- **版本**：1.0.0rc2，修改包与镜像恢复版验收候选。Windows 对 ext4 直接写入及 Ubuntu 真实分区应用仍禁用。
- **作者及版权署名**：Jianchao Liu。
- **项目许可证**：[MIT](LICENSE)。第三方依赖保留各自许可证。
- **界面语言**：当前为简体中文；双语 README 不代表已有英文界面。

## 功能与边界

| 功能 | 当前状态 |
|---|---|
| 磁盘、分区及卷识别 | 后台只读查询；通过稳定身份绑定访问目标 |
| Windows 浏览 | 目录分页、地址栏、历史导航、面包屑、属性及隐藏文件 |
| 文本、代码和图片预览 | 只读，具有字节、字符和像素限制，不执行文件 |
| 筛选与搜索 | 当前已加载条目筛选，以及显式启动的跨分区元数据搜索；支持取消与定位 |
| 复制与导出 | Windows → Windows；已验证 ext4 `/home` → Windows，默认不覆盖 |
| Windows 受控写入 | 非启动普通数据卷中的明确授权目录；支持新建、保存、重命名、同卷移动和文件/空目录删除 |
| ext4 读取 | pytsk3 只读后端，须验证身份、范围和文件系统；原始设备权限不足时明确拒绝 |
| ext4 写入 | **禁用**，没有实际写驱动接入，不能通过配置开启 |
| ext4 修改包暂存 | 进入目录后通过“ext4 暂存与修改包…”暂存五类操作并导出；Ubuntu 执行与恢复首版仅限显式注册的 loop 测试镜像，实机验收待完成 |
| 保护分区 | EFI、MSR、Recovery 等仅显示受限元数据，不开放普通写操作 |

GUI 不自动提权；Windows 实际 ACL 仍决定访问权限。应用不格式化磁盘、不修改分区表、不将磁盘离线、不自动挂载 Ubuntu，也不绕过加密或锁定。

## 安装与启动

需要 Windows x64、Python **3.11 或 3.12**，以及 Windows Storage PowerShell 模块。当前本机环境为 Python 3.12.8、PySide6 6.10.0。

如果已有本项目 `.venv`，直接运行，不要重复创建：

```powershell
cd D:\crossdisk_manager
.\.venv\Scripts\python.exe -m app.main
```

首次安装时，在实际项目目录使用普通 PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

若 Python 3.12 未注册到 `py`，使用其已安装 `python.exe` 的完整路径创建环境。无需激活虚拟环境，也无需更改 PowerShell 执行策略。

模拟模式不扫描真实磁盘：

```powershell
.\.venv\Scripts\python.exe -m app.main --demo
```

## 基本使用

1. 启动后选择普通 Windows 卷，使用地址栏和面包屑浏览；选中文件查看只读预览。
2. 工具栏筛选仅作用于当前已加载条目。“跨分区搜索”需手动开始，错误或预算停止时明确显示部分结果。
3. “复制/导出到 Windows…”将选定源复制到现有普通 Windows 数据目录；同名目录默认整目录跳过，不合并、不覆盖。
4. 写 Windows 文件需先选择普通非启动数据卷，再点击“配置 Windows 写入目录…”，选择目录并确认；操作在独立窗口进行。
5. 文本编辑限 2 MiB UTF-8，保存为无 BOM UTF-8，检测内容冲突并保留 `.bak`。永久删除需二次确认；没有通用撤销。
6. ext4 只读格式验证与写入准入互相独立；没有可开启的 ext4 写开关。真实 Ubuntu 读取权限及验证步骤见用户手册。

复制取消保留已完成文件，只清理任务自己的未完成临时文件；设备底层调用阻塞时，取消和关闭可能需要等待。复制暂不保留时间戳和属性。

## 配置与日志

- 配置：`%LOCALAPPDATA%\CrossDiskManager\config.json`。
- 日志：同目录 `logs\app.log`，轮转保留；帮助菜单可查看末尾 64 KiB。
- 配置 `read_only=true` 保护默认浏览模式；独立 Windows 写入上下文需额外确认，ext4 不受其授权。
- 不自动上传文件或日志，不自动后台监控全盘。日志不记录正文、令牌和完整敏感路径。

## 测试与构建

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

最近一次完整回归（2026-11-07）：**277 项通过，1 项因 Windows 符号链接创建权限跳过**；依赖检查通过。实际 exe 的 9 项黑盒检查通过，包含暂存面板导出、目录/预览/搜索及真实磁盘扫描导航。见 [rc2 交付记录](docs/RELEASE_RC2.md)。

从源码构建 Windows 文件夹式候选包：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m scripts.build_release
.\.venv\Scripts\python.exe -m scripts.smoke_frozen
.\.venv\Scripts\python.exe -m scripts.build_release --package-only
```

构建生成 `dist/CrossDiskManager/CrossDiskManager.exe`、Windows ZIP 和 SHA-256 文件。需保留整个解压目录，包括 `_internal`、许可与文档，不能只复制 exe。rc2 已在本地重新构建并验证，附带 Ubuntu 镜像执行工具；未公开发布。组合交付包通过 `python -m scripts.build_delivery` 生成，快速使用见 [QUICK_START_CN.md](QUICK_START_CN.md)。

## 验证状态

本机 Windows 11 的源码启动及 Windows/合成 ext4 镜像回归已有证据；**真实 Ubuntu 完整浏览/导出、回收站原生交互与恢复、独立 Windows 10/其他机器仍待验收**。镜像只读成功不能替代真实 ext4 写入兼容性验证。当前保持候选版标识。

## 文档

- [用户手册](USER_GUIDE.md)
- [安全边界](SECURITY.md)
- [支持矩阵](docs/SUPPORT_MATRIX.md)
- [ext4 写入可行性报告](docs/EXT4_WRITE_FEASIBILITY.md)
- [项目进度](docs/PROGRESS.md)
- [完整开发历史（中文归档）](docs/DEVELOPMENT_HISTORY.zh-CN.md)
- [第三方软件声明](THIRD_PARTY_NOTICES.md)

## 许可证

本项目自身源码采用 [MIT License](LICENSE)，Copyright (c) 2026 **Jianchao Liu**。依赖库、运行时及第三方代码继续适用其原有条款；项目的 MIT 许可证不重新许可这些组件。分发构建产物时应保留并遵守相应第三方声明及许可。
