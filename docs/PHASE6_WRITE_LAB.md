# 单文件写入实验：新建镜像专用

2026-11-06：用户确认上一轮 Ubuntu 预检全部 PASS，授权继续。结果 ZIP 未提供，未独立复核；此状态不等同于已审阅原始验收证据。

新增 scripts/write_lab.py，原 apply_bundle 仍只允许预检，不开放 --apply。

本实验自己生成新的 128 MiB ext4 镜像，只使用其中固定样本；不接受既有镜像、设备、修改包或用户目录参数。外部备份和 JSON 日志放在 /var/lib/crossdisk-manager-write-lab 下的独立随机目录。

流程：原始快照 → 正文/基本元数据备份及 fsync → 同目录临时文件 → 原状态复核 → 原子替换 → 结果校验 → 对照备份还原 → 新建 no-replace 发布 → 同名覆盖拒绝 → 撤销新建。读取校验后重新设置还原承诺的 atime/mtime。重建文件不保证原 inode/ctime。

运行方法：在 Ubuntu 本地解压目录打开终端：

```bash
sudo python3 -m scripts.write_lab --run-disposable-tests
```

完成后带回 CrossDisk_Write_Result_*.zip。该 ZIP 包含结果和操作日志。错误时保留工作目录，不自行重放中断操作。脚本结束尝试卸载并只检查 e2fsck，失败时不删除证据。

边界：这是单文件正常流程实验，不是通用安全写入执行器。恢复冲突仅覆盖快照不匹配判断，尚未测试并发写入或故障注入；没有中断后的 check/resume/rollback 命令，不保证断电自动恢复。拒绝的临时文件保留在测试镜像中，不按名称批量删除。不能用于真实数据。Ubuntu 实机结果尚待验证。

## 2026-11-06 Ubuntu 结果复核

已读取 CrossDisk_Write_Result_9c775744c5f6.zip，ZIP CRC 正常，write-report.json 与 journal.json 的 12 条检查和事件列表一致，全部通过。替换、还原、新建及撤销新建的 PREPARED 均先于 COMMITTED。备份哈希、原状态复核、不覆盖保护以及正文/权限/UID/GID/mtime/nlink 还原通过。报告包含卸载后五遍 e2fsck 输出，filesystem_check_ok=true，无执行或清理错误。Windows 本次仅复核报告，没有重跑 Linux 检查，结果包未包含最终镜像及备份正文。

结论：本次可丢弃镜像上的单文件正常写入与还原实验通过。不能据此认定中断恢复、故障注入、断电一致性或真实数据写入通过。restore-conflict-detected 仅验证错误快照与实际状态不同，不是完整并发拒绝试验。下一步应实现中断状态识别与受控恢复，再进行故障注入测试。机器可读复核记录：WRITE_LAB_RESULT_2026-11-06.json。
