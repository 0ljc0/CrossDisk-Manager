# 进程中断恢复实验

2026-11-06。上一轮正常写入实验已复核通过，本轮新增单文件替换的中断判定及实验内受控继续/还原。

Ubuntu 解压后运行：

```bash
sudo python3 -m scripts.recovery_lab --run-disposable-tests
```

工具只创建自己的普通测试镜像，不接受已有文件系统或目标参数。使用 Linux fork 子进程执行替换，分别在 PREPARED 持久化后发布前，以及原子替换和目录同步后、COMMITTED 日志前调用 os._exit 强制结束子进程。父进程从磁盘重新读取记录、备份和快照，不采用子进程返回的内存结果。

前置状态匹配且临时文件完整为 NOT_COMMITTED；发布后完整身份匹配且临时名称消失为 COMMITTED；备份无效、状态冲突或证据不足为 UNKNOWN，不能据此继续。实验只在前两类明确状态下重新复核并继续或还原，日志保存在镜像外。

结果：CrossDisk_Recovery_Result_*.zip，包含报告和各阶段 JSON 记录。无论 PASS/FAIL 都保留工作目录及 ZIP。

范围限制：这是进程退出测试，不是断电；未覆盖恢复执行期间再次中断、日志截断/丢失、ENOSPC/EIO、多操作事务。冲突测试目前为观察快照的负向判定，并非不合作外部进程的竞态实测。只验证正文和基本权限/所有者/mtime，不验收 atime 还原。没有可用于已有真实数据的 check/resume/rollback 命令。生产写入仍禁用。

## V2：恢复途中再次中断

上一轮 V1 由用户确认成功，未取得并复核恢复结果 ZIP；据用户授权继续，不将口头确认写成已复核原始报告。

V2 新增还原发布前退出（93）、还原发布后完成日志前退出（94）。父进程重新读取持久化记录、备份及磁盘快照，判定 NOT_COMMITTED 或 COMMITTED 后才继续。另写入截断/修改的日志副本并重新读取；缺失和损坏备份采用传入缺失值/损坏字节的负向判定。所有拒绝都须为 UNKNOWN。它们不等同于真实存储丢失和介质故障。

使用 CrossDisk_Recovery_V2_Ubuntu_Kit.zip，命令仍为 sudo python3 -m scripts.recovery_lab --run-disposable-tests。输出 CrossDisk_Recovery_Result_*.zip 中报告 version=2。

上文 V1 的“未覆盖恢复执行期间再次中断”由本轮实验扩展；V2 Ubuntu 结果仍待验证。ENOSPC/EIO、断电、真正并发写入和生产恢复命令仍未交付。摘要锚点只检测意外损坏，不能抵抗同时篡改锚点和日志。
