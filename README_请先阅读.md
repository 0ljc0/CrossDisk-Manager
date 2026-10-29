# CrossDisk Manager｜分 12 次开发任务（2026-10）

本任务包是交给 Claude Code / 其他代码助手逐次执行的**开发指令集**，不是已开发完成的软件。建议一次只提交一份任务，不要一口气把 12 份全部交给模型实施。

## 项目目标

在 Windows 10/11 64 位上构建 PySide6 GUI，在一张界面内展示全部物理磁盘、分区和有权限访问的文件。Windows NTFS/FAT/exFAT 使用系统原生 API 读写；Ubuntu ext4 先使用 pytsk3 **只读**浏览和导出，再单独研究合规、兼容且已测试的写入后端。

**定义“所有分区”：** 全部分区可发现、展示状态；不是承诺所有分区一定可挂载或读写。MSR 通常无普通文件树；加密/锁定卷、EFI/Recovery、未知和不兼容文件系统必须按权限和风险限制。

## 已知本机验证环境

- 物理磁盘：`磁盘 0`，YMTC 固态硬盘约 953.87 GiB，GPT。
- C: 分区 3，NTFS 约 300 GiB；D: 分区 4，NTFS 约 501.64 GiB。
- Ubuntu：磁盘 0、分区 6、约 150 GiB，系统为 Ubuntu，预期文件系统 ext4。
- EFI：分区 1；MSR：分区 2；Recovery：分区 5。
- 已通过 Python + `pytsk3` 只读读取 Ubuntu；当前脚本位于 `D:\谷歌浏览器\read_ubuntu_partition6.py`（请核实本机路径），任务 05 复用但不得依赖固定分区编号。
- **安全要求：** Windows 和 Ubuntu 共用正在使用的物理系统盘，不尝试 `wsl --mount` 附加这块磁盘，不将系统盘离线，不写原始物理扇区，不改分区表。

以上是本机测试资料，不应成为软件全局写死的常量。

## 初始化方式

在 Windows PowerShell 里自选项目目录，推荐 `D:\CrossDisk_Manager`；克隆或复制本任务包里的 `CLAUDE.md` 到**项目根目录**，`docs/tasks` 一并复制。之后让 Claude Code 先读 `CLAUDE.md` 和指定的当次任务文档。

项目目录不是代码写死值，可改为其他位置；**不要**把代码开发目录放在 Ubuntu 真实分区中做写入测试。

## 推荐执行顺序

| 序号 | 文件 | 阶段结果 | 是否需管理员 |
|---|---|---|---|
| 01 | `01_环境与项目骨架.md` | 程序可启动、测试与日志成型 | 否 |
| 02 | `02_图形界面框架.md` | 中文三栏 GUI 可交互 | 否 |
| 03 | `03_磁盘及分区识别.md` | 全部磁盘分区可显示 | 通常否，必要时才提升 |
| 04 | `04_Windows原生文件浏览.md` | C/D 盘只读浏览 | 否 |
| 05 | `05_Ubuntu_ext4只读接入.md` | 识别并浏览 Ubuntu /home | 读取物理磁盘时可能需要 |
| 06 | `06_统一文件导航与权限.md` | 统一操作 Windows/ext4 | 按后端需求 |
| 07 | `07_文件预览与文本查看.md` | 代码/文本/图片预览 | 否 |
| 08 | `08_搜索筛选与索引.md` | 按名称、扩展名搜文件 | 按后端需求 |
| 09 | `09_复制导出与任务队列.md` | Windows 与 Ubuntu 间只读导出 | 按源后端需求 |
| 10 | `10_Windows安全写入与编辑.md` | Windows 分区可创建/编辑/删除 | 受文件权限限制 |
| 11 | `11_ext4受控写入适配与验证.md` | 驱动能力评估，满足条件才打开写入 | 取决于已验证驱动 |
| 12 | `12_测试验收与打包发布.md` | 可靠性测试、exe/安装包、说明 | 测试部分可能需要 |

## 每次如何向 Claude Code 发送任务

进入项目文件夹，启动 Claude Code，然后发送以下模板（把 XX 换成当前任务编号）：

```text
请先阅读项目根目录 CLAUDE.md、README_请先阅读.md 和 docs/tasks/XX_对应文件.md。
仅实施这一份任务，不提前做后续功能。先检查已有代码和 git 状态，复述本次修改计划，再实施、运行相关检查，最后说明修改文件、运行命令、测试结果和遗留问题。
务必遵守只读和写入保护要求；禁止任何分区格式化、分区表更改、磁盘离线、wsl --mount 系统盘及原始扇区写入。
```

**每完成一次任务，先验收，再提交一次 Git commit，再发下一份文档。**

## 项目文件结构建议

```text
D:\CrossDisk_Manager\
  CLAUDE.md
  README_请先阅读.md
  docs\tasks\01_环境与项目骨架.md ... 12_测试验收与打包发布.md
  app\
    main.py
    core\           # 模型、统一接口、能力检查、安全策略
    services\       # 磁盘检测、搜索、预览等
    backends\       # windows_native、ext4_readonly、ext4_optional_write
    ui\             # 主窗口、分区树、文件表、预览面板
    jobs\           # 导出、复制、取消、进度
  tests\
  requirements.txt
  pyproject.toml
  README.md
```

## 跨阶段关键验收指标

1. 非管理员启动也能正常显示 GUI、C/D 磁盘；提升权限只为必要的原始磁盘读取。
2. 重新插入硬盘或重启后，分区标识不得依赖固定的 `磁盘0/分区6`。
3. ext4 只读后端必须零写入，并能正确浏览 `/home`，导出到 Windows 非已有文件。
4. 原生 Windows 写入的失败路径不会损坏已有文件；永久删除要显式确认。
5. 未经过兼容性验证的 ext4 写入 UI **一律保持禁用**。
6. EFI、MSR、Recovery 和不受支持/加密分区不得被普通功能写入。

## 可信技术资料

- Windows 分区信息：<https://learn.microsoft.com/en-us/powershell/module/storage/get-partition>
- Microsoft WSL 挂载限制：<https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk>
- Qt for Python：<https://doc.qt.io/qtforpython-6/>
- The Sleuth Kit：<https://www.sleuthkit.org/>

## 费用建议

为控制 API tokens，每次只给模型一个任务文件；让模型只读取修改相关的文件；保存阶段总结、检查结果后开启新会话，避免每轮重新分析整个工程。
