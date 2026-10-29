# 任务 05 验证记录

日期：2026-10-29。Python 3.12.8、PySide6 6.10.0、pytsk3 20260715（cp312 Windows x64 wheel）。

**代码与镜像验证完成；真实 Ubuntu 分区的人工验收尚未完成。**
按任务文档“真实分区仅人工只读验收”，本次没有在自动化脚本中读取真实 Ubuntu 原始分区，也没有默认提权 GUI。

## 自动化结果

- 全套回归：**100 passed, 1 skipped in 20.28s**。
- 最后 Unix 权限提示/兼容字段调整后的 ext4 专项：**24 passed in 3.61s**。
- `python -m pip check`：`No broken requirements found.`。
- 跳过项仍为任务 04 的循环符号链接创建测试（当前 Windows 令牌缺少创建权限，WinError 1314），没有提权；ext4 镜像内链接测试正常通过。

所有 ext4 自动化测试使用真实 pytsk3 库和 `tests/ext4_fixture.py` 在临时目录构造的 4 MiB 普通 `.img` 文件。镜像含 extent 根目录 `/`、`/home/demo`、中文空格文件名、隐藏文件、短文本和循环链接；生成器按 ext4 元数据布局构造字节，不运行磁盘格式化工具，不挂载任何设备。它是最小无日志测试文件系统，不代表完整 Ubuntu 特性覆盖。

验证范围：

- `/` 列出 home，`/home` 列出 demo；中文/隐藏条目、分页、stat、目录进入、地址 `/home`、链接拒绝和所有写入按钮禁用。
- 普通文件流式读取与 EOF，损坏 inode、读取提前结束、路径不存在/遍历拒绝。
- LUKS、LVM、未知魔数、加密特征、不干净状态、超级块越界等全部失败，不恢复、不写入。
- 模拟当前清单中 GUID、卷标、偏移、设备缺失变化；任何失败都发生在设备打开前。磁盘重编号按稳定身份重新匹配，不依赖原始编号。
- 内存 GPT 样本覆盖 512/4096 字节扇区，核对打开设备后的 GPT CRC、GUID、分区位置/大小；错位或校验失败时禁止文件系统读取。
- 非零镜像分区偏移（1 MiB）读取正确，边界之外的请求被拒绝。
- 同一扫描会话的 ext4 卷标/UUID/特征指纹变化导致拒绝读取。
- 镜像 SHA-256 在只读操作前后不变；close 后能立即重命名/清理镜像，重复关闭可用。
- GUI 真实子进程使用合成镜像展示根、home、demo；取消/超时及原有 Windows 测试均通过。

## 样本读取与 Windows 新文件导出

执行 `python -m scripts.capture_ext4_image_ui` 成功；通过 `validate_sample` 从镜像中的 `/home/demo/sample.txt` 流式读出到独立 Windows 临时目录中的新文件，使用 `xb`，核对源与导出散列及长度，随后清理。

- 样本长度：**28 字节**。
- SHA-256：`18960b19839c0e31caa478ef8b3b09d18dbf507388789a173311ad2d383a3a80`。
- 内容与 fixture 中明确的 UTF-8 样本文本相同；没有输出或复制真实用户文件。
- 图形截图：`screenshots/task05-image-root.png`、`task05-image-home.png`、`task05-image-files.png`；已打开检查 home 截图，界面标明“合成镜像（非真实磁盘）”。

## 已阅读的已有脚本

`D:\谷歌浏览器\read_ubuntu_partition6.py` 存在，已只读阅读，未修改，也未执行其真实磁盘读/导出命令。复用其 Img_Info → FS_Info(offset) → read_random 方式，删除业务对固定磁盘 0/分区 6 的依赖，增加身份、GPT、格式与边界校验。

## 仍需用户人工验收

1. 普通权限启动 `python -m app.main`，点击本次扫描得到的 Linux 候选；应先显示待验证，成功后为只读 ext4。
2. 若设备访问被拒绝，保持 GUI 普通权限；按 README 的独立工具说明，在用户明确打开的管理员 PowerShell 中仅运行只读工具。当前没有管理员代理向普通 GUI 回传数据的 IPC 服务。
3. 通过独立工具的 `--list-candidates` 取得当次稳定 ID，明确选择正确分区，再人工执行 `/`、`/home` 和自选普通样本文本的 sample 校验。不要把磁盘/分区编号当作长期标识。
4. 人工确认真实用户目录、样本文本字节数/散列及只读 UI 行为。不要为验收主动改变真实卷标或分区偏移；这些拒绝路径已用样本验证。

尚未证明真实 Ubuntu 分区的 ext4 特征满足本后端限制，不能宣称已完成实盘浏览。LUKS/LVM、日志恢复、加密、inline/casefold/bigalloc 等特征拒绝；镜像测试不代表这些特性受支持。

没有 ext4 写入、重命名、删除实现；没有格式化、分区表更改、磁盘离线、wsl --mount 或原始扇区写入。任务 06 及后续功能未开发。
