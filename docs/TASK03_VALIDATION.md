# 任务 03 本机核对记录

日期：2026-10-29；Python 3.12.8，PySide6 6.10.0。

固定 Storage 查询与真实 Qt 后台清单均发现 **1 个物理磁盘、6 个分区、3 个 Windows 卷**。
型号 YMTC YMSS2ED08D25MC，约 953.87 GiB，GPT。
查询宿主的 `WindowsPrincipal.IsInRole(Administrator)` 返回 **False**，没有请求 UAC 提权。

另行执行以下命令，并与服务解析结果逐项核对；6 个分区的编号、大小和起始偏移一致：

```powershell
Get-Partition | Sort-Object DiskNumber,PartitionNumber |
    Format-Table DiskNumber,PartitionNumber,DriveLetter,Offset,Size,IsHidden,GptType -AutoSize
```

| 磁盘 | 分区 | 盘符 | Offset（字节） | Size（字节） | 隐藏 | GPT 类别 |
|---|---|---|---:|---:|---|---|
| 0 | 1 | 无 | 1048576 | 272629760 | True | EFI |
| 0 | 2 | 无 | 273678336 | 16777216 | True | MSR |
| 0 | 3 | C | 290455552 | 322123595776 | False | 普通数据 |
| 0 | 4 | D | 322414051328 | 538631848448 | False | 普通数据 |
| 0 | 5 | 无 | 1022112038912 | 2097152000 | True | Recovery |
| 0 | 6 | 无 | 861046571008 | 161065467904 | True | Linux 数据，文件系统待验证 |

分区 6 约 150.00 GiB，其 GPT 类型是 Linux 数据，Windows Storage 未报告文件系统；应用显示“未识别”，因其隐藏标志显示“受保护”。本阶段没有读取其文件或推断为 ext4。
分区编号仅在本记录中说明实机快照，源码未固定磁盘/分区号、容量或用户设备 GUID。

## 验证范围

- 自动化：`python -m pytest -q`，**45 passed in 7.86s**。覆盖原有任务回归、单对象/数组/null、无盘符卷关联、设备重编号与替换、身份缺失、重复身份、不一致清单、权限拒绝、缺少 PowerShell、超时、后台响应、刷新/拔出模拟及扫描期间退出。
- 实机：后台 Qt 线程查询成功，点击分区 6 展示大小、偏移和 GPT/Partition GUID；截图检查后修正长标识符截断与树列宽，结果见 `screenshots/task03-inventory.png`。
- 依赖：`python -m pip check` 返回 `No broken requirements found.`。
- Git：`git diff --check` 无空白错误，仅有系统默认换行转换提示。
- 缺少 PowerShell、权限不足、设备拔出等异常用样本和假服务模拟，没有改变本机设备状态或账户权限。
- 尚未在多物理盘、实际热插拔、独立 Windows 10 设备上验证；这些不应被视为已验收。

没有原始设备写接口、磁盘格式化、分区表更改、盘符分配、隐藏标志修改、磁盘离线、系统盘挂载或 ext4 写入实现。
