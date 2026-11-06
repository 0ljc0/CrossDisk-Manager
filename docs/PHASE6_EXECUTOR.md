# Ubuntu 修改包执行与恢复：loop 测试镜像版本

2026-11-07。本轮把 schema 3 修改包、固定注册、目录 FD、私有 staging、备份、文件操作和恢复命令整合起来。Ubuntu 实机端到端验收仍待完成。

## 已实现

- 默认 apply_bundle 仍只预检。显式 --apply 必须同时确认 UUID 和维护窗口。
- 旧 preflight-only 注册不能写入；只有管理员新注册时传 --enable-bundle-apply 的 bundle-test 目标可执行。它必须是内核 loop 设备，绑定普通镜像文件的设备/inode/大小，真实分区无法取得该能力。
- 新建、替换、普通文件删除、单层目录创建和同目录普通文件重命名。每次提交前重查状态；新建和重命名使用原子 no-replace。
- 覆盖/删除前在外置备份目录保存正文及基本元数据，校验、同步后将备份身份写入执行记录。备份清单包含原路径、父目录身份、原快照及 atime。
- 固定注册表记录每个 bundle ID 和 manifest 摘要，执行 JSON 具有链式事件摘要，注册表锚定整个执行记录的摘要。重复已完成/已还原的同一包不会重新操作目标；换 ID 的相同语义请求也拒绝。
- 各项逐一执行，失败停止并标记 NEEDS_RECOVERY；不能保证多个文件组成事务。
- recover_bundle 的 --check 输出当前观察结果和计划摘要；显式 --resume 或 --rollback 必须确认当前计划摘要、UUID 和维护窗口。重新检查后再写入，UNKNOWN 不提供 force 绕过。
- 还原按逆序进行：删除新建文件、恢复替换和删除的正文/基本属性、反向 no-replace 重命名、删除身份未变化且为空的新目录。

## 一键验收

解压 CrossDisk_Executor_Ubuntu_Kit.zip，在解压目录运行：

```bash
sudo python3 -m scripts.executor_lab --run-disposable-tests
```

脚本自己生成新 128 MiB 镜像，使用真实命令入口测试默认预检、错误确认拒绝、五类操作应用、重复执行不重放、五类操作还原，以及在文件发布后/提交日志前退出进程，再 check、显式 resume、rollback。共 11 项检查。结束后卸载并只检查 e2fsck。

生成 CrossDisk_Executor_Result_*.zip，包含报告、运行状态和备份元数据。把该 ZIP 带回 Windows 复核。镜像及正文备份保留于 /var/lib/crossdisk-manager-executor-lab 下，不自动删除。

## 独立命令

先通过 register_target 在原有确认参数之外增加 --enable-bundle-apply。该选项只适用于已挂载的 loop 测试镜像；测试脚本会代为注册自己的镜像，不需要手工填写。

```bash
sudo python3 -m scripts.apply_bundle --bundle /path/to/bundle --target test-root --dry-run
sudo python3 -m scripts.apply_bundle --bundle /path/to/bundle --target test-root \
  --apply --confirm-uuid 实际UUID --confirm-maintenance-window

sudo python3 -m scripts.recover_bundle --target test-root --bundle-id 实际包ID --check
sudo python3 -m scripts.recover_bundle --target test-root --bundle-id 实际包ID \
  --resume --confirm-plan 当前计划摘要 --confirm-uuid 实际UUID --confirm-maintenance-window
sudo python3 -m scripts.recover_bundle --target test-root --bundle-id 实际包ID \
  --rollback --confirm-plan 当前计划摘要 --confirm-uuid 实际UUID --confirm-maintenance-window
```

## 范围与保守限制

首版最多 100 项操作、512 MiB payload。存储、权限、名字、元数据范围沿用注册与预检要求；必须处于无其他写入者的维护窗口，不承诺内容级原子 compare-and-swap。

注册仍绑定本次启动、挂载和目录身份；卸载重挂、重启、目录替换后不自动重新绑定。本版本不提供生产身份迁移工具。

默认拒绝模糊恢复：删除或 rmdir 完成但完成日志尚未持久化时，仅凭对象消失不足以证明归属，检查为 UNKNOWN。临时文件创建过程中退出、初始化中断、执行 JSON 与注册锚点不同步、日志损坏等也可能需要人工核查。没有重置或强制覆盖入口，不能把“有恢复命令”理解为所有崩溃都可自动修复。

恢复在应用前状态可证明时继续；回滚已经提交的操作。未提交操作留下的内部临时文件会保留为证据，不按文件名前缀清理。回滚重建文件不保证原 inode/ctime/birth time 或父目录时间；仅还原正文及受支持的 mode/UID/GID/mtime/atime。哈希读取可能更新 atime，还原提交后重新设置承诺的时间。

本轮未测试断电、真实坏块、生产数据目录、跨启动迁移。执行器当前的目标是实际读取 Windows 修改包、在隔离镜像内形成应用/恢复闭环。Windows GUI 可导出该格式，真实 Ubuntu 分区写入继续禁用。

本机验证：完整回归 276 passed, 1 skipped；随后补充恢复采纳结果前必须同步父目录的专项测试。交付包逐文件摘要、Python 3.10 语法和独立解压后的命令入口均通过。Ubuntu 端到端 11 项用例尚待实测，不将本机策略测试作为 Linux 写入验收。

接口依据：[Linux loop backing_file ABI](https://android.googlesource.com/kernel/common/+/49289b1fa5a67011/Documentation/ABI/testing/sysfs-block-loop)、[Linux renameat2](https://man7.org/linux/man-pages/man2/renameat2.2.html)。

## 2026-11-07 Ubuntu 端到端结果复核

已收到 CrossDisk_Executor_Result_d63b8413935d.zip，CRC 正常。11 项全部通过，默认预检与错误 UUID 拒绝、五类操作应用、重复执行保护、还原后不重放、中断发布识别、显式继续及继续后还原均有对应报告。两次执行最终为 ROLLED_BACK，各 5 个原操作和 5 个 undo 均为 COMMITTED。

已独立核对两份 run.json 的事件链、报告中的最终执行摘要、恢复计划摘要，以及四份备份元数据文件的摘要和原快照对应关系。中断检查为首项 COMMITTED、后四项 PENDING；后续完成和还原结果一致。报告记录卸载后 e2fsck 检查通过，无执行或清理错误。

本次 Windows 未重新挂载镜像；结果包不含最终镜像、备份正文或主机固定注册表，因此本次复核范围为报告与随附 JSON 的一致性，不能宣称独立验证所有落盘正文或注册锚点。通过范围仅为本轮 loop 测试镜像端到端闭环，不开放真实分区。机器可读记录：EXECUTOR_RESULT_2026-11-07.json。
