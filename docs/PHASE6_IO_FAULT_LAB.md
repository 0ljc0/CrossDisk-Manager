# 空间不足和读写故障实验

2026-11-07。前一轮恢复 V2 用户确认通过，结果 ZIP 尚未独立复核；本轮按用户授权继续。

在 Ubuntu 本地解压目录运行：

```bash
sudo python3 -m scripts.io_fault_lab --run-disposable-tests
```

脚本创建自己的新 128 MiB 镜像，不接受既有镜像或设备参数。请保证 Ubuntu 宿主有至少 512 MiB 可用空间。镜像、失败临时文件及日志均保留；不自动删除失败证据。

七个场景：

- 将测试镜像写满，实际触发 ENOSPC；尝试写替换临时文件再次遇到 ENOSPC，验证原文件未改变。只填满自己的镜像，不填满宿主或备份卷。
- 在读取备份源、同步备份、同步临时文件、准备日志写入、替换后父目录同步和完成日志写入六个边界分别注入软件 EIO。

提交尝试前的错误必须 FAILED_STOPPED，原文件匹配旧快照；提交尝试后的错误必须 NEEDS_RECOVERY，即使眼下内容已匹配新快照，也不能宣称完成、自动重试或执行后续操作。每项状态及观察快照写入外置 JSON，最终卸载后执行只检查 e2fsck。

结果 CrossDisk_IO_Result_*.zip 放回 Windows 项目目录进行复核。工具只运行实验，没有生产 apply 或恢复入口。

边界：EIO 为软件异常注入，不是物理介质坏块或内核真实返回 EIO；未填满备份/状态文件系统，不测试断电。FAILED_STOPPED 并不自动授权重新运行；NEEDS_RECOVERY 需要后续恢复检查，本脚本保留这些文件而不自动还原。本轮 Ubuntu 实机结果待验证。

## 2026-11-07 Ubuntu 结果复核

已收到 CrossDisk_IO_Result_0312b10552a0.zip，CRC 正常。七个场景全部通过，单项 JSON 与总报告一致。真实镜像 ENOSPC errno=28；六个软件 EIO 均为 errno=5。提交前失败为 FAILED_STOPPED，观察正文哈希与固定原样本一致；提交后父目录同步和完成日志错误为 NEEDS_RECOVERY，观察快照与 PREPARED 的 after 匹配，未错误记为 COMMITTED。全部禁止自动重试和后续执行。报告记录卸载后五遍 e2fsck 检查通过，无执行或清理错误。

本次 Windows 仅核对日志，结果包未含最终镜像或备份正文；没有重新运行 Linux 检查。通过范围为测试镜像内的 ENOSPC 和软件 EIO 边界处理，不等同于物理设备故障或断电验收。机器可读记录 IO_RESULT_2026-11-07.json。
