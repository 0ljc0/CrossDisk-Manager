# 第六阶段 G0 实施记录与设计补充

日期：2026-11-05。对应用户提供的 V1.2 / schema 3。

## 当前证据

新增 app/services/file_snapshot.py：独立实验性只读快照接口，流式哈希，读取前后复核元数据。它不授权暂存导出或任何磁盘写入。
生产环境 pytsk3 20260715 提供 mtime_nano、nlink、addr；mode 实测仅为权限位，转换时结合普通文件类型构造完整 POSIX mode。
合成镜像测试覆盖 123456789、987654321、零纳秒，nlink=1/2，UID/GID、inode、mode、正文哈希以及镜像不变。
上述为初始合成夹具证据；2026-11-06 已完成用户提供的 Linux 镜像对照，结果见下节。本机 WSL 查询未返回可用发行版，未安装或启用任何系统组件。

## 下一步跨系统对照

在原生 Ubuntu 的可丢弃 ext4 镜像上按 V1.2 第 5.3 节准备样本；使用 os.fstat 的完整字段和文件 SHA-256 生成镜像外 UTF-8 JSON：顶层 files 对象，键为文件系统内相对路径，值为 kind、size、sha256、mode、uid、gid、mtime_ns、nlink、inode。kind 固定 regular_file。
真值应覆盖两种非零纳秒、整秒、链接数 1/2、空文件、中文名、大文件及不同所有者和权限；记录 Linux 和工具版本。同步卸载后记录镜像摘要，将普通镜像与真值报告交给 Windows。

运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.g0_compare --image <普通测试镜像路径> --truth <Linux真值JSON路径>
```

比较器仅输出对照结果，不因输出无差异而自动授权写入。需人工核实 Linux 来源、覆盖矩阵、同一镜像摘要与全部字段。禁止将真实设备路径用作输入。

## 状态契约补充

Bundle：PREFLIGHT_OK -> APPLYING -> COMPLETED；执行失败且确定未提交为 FAILED；提交或证据不确定为 NEEDS_RECOVERY；显式还原全部完成才为 ROLLED_BACK。
Operation：PENDING -> PREPARED -> COMMITTED；确定失败为 FAILED；结果不确定为 UNKNOWN。UNKNOWN 仅属于操作，所属 bundle 必须转 NEEDS_RECOVERY。
BACKUP_READY 是日志事件，不是独立终态。任何 UNKNOWN、失败未解决或日志缺失均阻止普通 apply。恢复 check 不修改提交状态；resume/rollback 必须持锁并重新核对计划。

## mkdir 顺序

预检父目录与目标不存在、注册权限及继承属性；持久化意图；受控父目录 FD 下创建 0700 目录；记录新目录身份，设置并复核 UID/GID/mode 和扩展属性；同步新目录、父目录和完成日志。创建成功但身份记录未持久化的中断不得猜测归属，应转 UNKNOWN。撤销只允许已确认身份且为空的目录。

## 还原后的再次申请

原 bundle 永不重放。语义摘要相同且旧运行未还原时拒绝普通 apply。已验证 ROLLED_BACK 后允许显式管理员重新申请流程建立新运行代次，关联旧运行、重新采集快照与授权；不得仅更换 bundle ID 绕过。此流程尚未实现，第一版没有该入口时须明确报告不支持重新申请，而不能静默放行。

## 实施顺序及未完成项

G0 Linux 真值验收优先；后续为 schema 校验、Linux 注册/路径预检、单文件提交/备份/恢复、其余操作、GUI。
管理员初始化工具、recover_bundle 的 check/resume/rollback、运行代次管理均为明确交付项。当前未实现执行器，未开展真实分区写入、断电或 Linux 挂载测试。

## 2026-11-06 实际跨系统验收

G0 快照能力通过本次测试范围内验收。用户带回根目录 g0.img、truth.json、e2fsck.txt。Linux 6.8.0-138 / Python 3.10.12；Windows Python 3.12.8 / pytsk3 20260715。128 MiB 镜像摘要与 Linux 封存报告一致，Windows 读取前后不变。

6 个路径、每项 10 个字段全部一致，differences=[]。覆盖纳秒 123456789/987654321/0、nlink 1/2、共享 inode 的硬链接、UID/GID 1000/1001、0600/0640/0644/0750、空文件、中文空格名和 16 MiB 内容。Linux 报告的 e2fsck 退出码为 0，随附五遍检查文本未报告错误；本次 Windows 未重新执行 e2fsck。机器可读结果：G0_RESULT_2026-11-06.json。

此结论只验证当前版本在本镜像上的只读快照能力；不验证实际写入、恢复或断电一致性，不保证任意 ext4 特性组合。升级读取器后需复验。未提供移除硬链接后的第二阶段镜像，因此不宣称完成链接增删复测。下一阶段可进入 schema 3 修改包校验和预检开发；真实 ext4 写入仍禁用。
