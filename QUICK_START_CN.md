# CrossDisk Manager 1.0.0rc2 快速开始

本地验收候选版，未签名、未公开发布。Windows 可以浏览 ext4、暂存修改并导出包；Ubuntu 应用与恢复目前只允许显式注册的 loop 测试镜像，真实分区应用仍禁用。

## Windows

完整解压 Windows ZIP，双击 CrossDiskManager 文件夹中的 CrossDiskManager.exe。保留同目录 _internal、docs 和 third_party，不要只复制 exe。无需另装 Python。

选择可验证的 ext4 来源并进入数据目录，点击“ext4 暂存与修改包…”。输入相对路径，使用本地文件新建或替换内容，也可暂存删除、建目录和同目录重命名。确认 UID/GID 和权限。列表显示的状态均为“尚未应用”。

点击“导出修改包…”，选择父目录和一个尚不存在的新目录名。未导出草稿关闭时会提示；导出后的包与当前会话独立。暂存面板不直接写入 ext4。

源设备读取权限不足会明确拒绝，程序不自动提权。Windows 普通数据目录的受控写入仍需单独配置。

## Ubuntu 测试镜像验证

Windows 包的 Ubuntu-tools 目录包含 CrossDisk_Executor_Ubuntu_Kit.zip；也可以使用交付包中单独提供的同名 ZIP。将其复制到 Ubuntu 本地目录并解压，在解压目录打开终端：

```bash
sudo python3 -m scripts.executor_lab --run-disposable-tests
```

该命令自动新建测试镜像和注册项，执行五类操作应用、还原、重复执行保护和中断后继续测试。结果为 CrossDisk_Executor_Result_*.zip。它不接受既有分区或镜像作为格式化目标。

手工注册及将 Windows 生成的包应用到已注册测试镜像，见 docs/PHASE6_EXECUTOR.md。Windows 读取镜像与 Ubuntu 挂载镜像必须是同一文件系统、同一目录根；Windows 生成后不要复制/重建原文件改变快照。应用前需停止其他写入者，并按预检报告确认。不能把真实 Ubuntu 分区当作本版可写目标。

## 结果与限制

本版已取得 G0 跨系统快照、预检、单文件写入与恢复、I/O 故障及修改包执行器的镜像报告；部分早期恢复实验只由用户口头确认，证据范围见 docs 下各阶段记录。Windows 打包程序的实际检查项见 docs/FROZEN_SMOKE_1.0.0rc2.json（组合交付包内也单独保存为 FROZEN_SMOKE.json）。

不是跨多文件事务。UNKNOWN、损坏日志或注册映射变化可能需要人工核查，无强制覆盖或自动回滚开关。未完成断电、真实坏块、跨启动迁移或真实数据目录写入验收。独立 Windows 10/其他电脑兼容性仍待验证。

退出前等待后台任务完成。移走或删除整个程序目录即可卸载；用户配置和暂存工作目录位于 %LOCALAPPDATA%\CrossDiskManager，导出包、备份和 Ubuntu 实验材料不会随卸载自动删除。
