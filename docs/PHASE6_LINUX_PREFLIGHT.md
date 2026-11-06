# Ubuntu 目标注册与只读预检

实现日期：2026-11-06。此版本只交付注册与预检，没有实际应用、备份复制或恢复入口。

## 已实现的行为

- `scripts.register_target`：管理员注册既有专用测试目录、UUID、目录 inode、挂载信息、UID/GID/权限集合，以及外置 ext4 状态和备份目录。
- 固定控制位置：`/etc/crossdisk-manager/targets.json`、`/var/lib/crossdisk-manager/registry/registry.json` 和 `/run/lock/crossdisk-manager/`。不能从修改包、环境变量或预检命令改位置。
- 注册文件与锚点分别持久化，摘要不一致或任一缺失时拒绝自动重建。初始化只允许两个记录都不存在的明确管理员操作；不提供重置功能。
- 使用全局注册锁、文件系统锁和目标锁。首版保守串行化所有预检；锁仅协调遵守本协议的本机进程。
- 同文件系统重叠根及完整根挂载别名不能形成第二个注册；状态/备份目录不能互相重叠或通过别名复用。
- Linux `openat2` 配合目录 FD、NO_SYMLINKS、NO_MAGICLINKS、BENEATH 和 NO_XDEV，目标内不能跨挂载点。接口不可用即拒绝，不回退到字符串检查。
- 文件先以 O_PATH 确认普通文件类型，再通过受控 FD 读取，避免先打开设备或阻塞在 FIFO 上。挂载、目录名绑定在预检结束前再次检查。
- 核对真实 ext4 挂载、FSROOT、打开目录设备号、当前命名空间及可发现设备的 UUID 歧义；完整根 bind mount 不被当作“非绑定挂载证明”。
- payload 从安全打开的源复制到 root 私有 staging，同步前核对大小和哈希；随后保留私有副本，不把源路径再次打开当作可信内容。
- 逐项检查原始十字段快照、新建目标不存在、重命名目标不存在、父目录存在及元数据授权。拒绝硬链接、ACL/xattr、特殊权限、不支持的 inode flags 和非零 project ID。
- 报告分别返回 MATCH/CONFLICT；`apply_allowed` 始终为 false。没有 `--apply` 参数。
- 已登记 bundle ID 不能绑定另一份 manifest；同一份包允许再次只读检查。旧报告缺失、损坏或上次进程在记录完成前中断时拒绝继续，保留证据。

## 范围与未验收事项

这是预检协议，不是写入状态机。PREFLIGHT_OK 仅表示本次观察满足条件，不能复用为日后的写入许可；后续实现写入时必须重新检查。

备份目录当前只检查身份、隔离和预计空间，不实际复制备份。执行日志、COMMITTED、恢复、断电一致性和管理员迁移仍未实现。本阶段不声称完成 V1.2 所有写入要求。

注册保守绑定当前 boot ID、挂载 ID、设备号、挂载选项和目录身份。重启、卸载重挂或根目录替换后，原注册不可自动复用。没有普通命令解除此拒绝；生产用持久身份迁移将单独设计。一键验证每次使用新的随机注册，结束后保留记录，不自动删除历史控制文件。

运行要求：原生 Linux，64 位 x86_64/aarch64 ABI，root，支持 openat2 的内核；当前验收目标是 Ubuntu 22.04。WSL、未知架构及接口不支持均拒绝。Python 3.10+ 标准库即可，不依赖 PySide6/pytsk3。aarch64 仅实现 ABI 分支，未取得实机验证证据。

状态与备份目录要求 root:0700，祖先不能由普通用户写入；状态/备份必须位于目标文件系统之外的本地 ext4。目标是 loop 镜像时，宿主 ext4 可供功能测试，但不代表物理设备故障隔离。普通 NTFS/exFAT/FAT 可以运输 bundle；FUSE（包括常见 ntfs-3g 的 fuseblk）输入须先复制到 Ubuntu 本地 ext4。

单次 staging 上限 512 MiB，清单 4 MiB、1000 操作。预检会写控制记录、私有暂存和报告，不主动修改目标内容或目录结构；读取可能改变 atime。维护窗口不能由程序证明，必须关闭其他写入者。

## 一键 Ubuntu 验证

将 `CrossDisk_Preflight_Ubuntu_Kit.zip` 解压到 Ubuntu 本地目录，在解压目录打开终端：

```bash
sudo python3 -m scripts.preflight_lab --run-disposable-tests
```

脚本创建自己的新 128 MiB 普通镜像和随机工作目录，不接受既有镜像或真实设备作为格式化参数。它也会创建上述固定控制目录和新的测试注册。样本写入只发生在新镜像中，预检不应用任何修改包。

测试包括五种操作正常预检、重复预检、错误 UUID、正文冲突、目标存在、越权所有者、符号链接父目录、缺失父目录、硬链接、FIFO、扩展属性、损坏 payload、跨挂载点和同 bundle ID 不同清单。

结束后尝试卸载专属测试挂载和解除 loop，执行只检查 e2fsck；不自动删除镜像或证据。在解压目录生成 `CrossDisk_Preflight_Result_<随机编号>.zip`。无论显示 LAB: PASS 或 FAIL，都把该 ZIP 带回 Windows，进行实测结果审查。若提示挂载清理失败，保留终端输出和工作目录，不自行格式化或删除。

## 独立命令（不需要为一键验证手工执行）

管理员预先准备 root:0700 的外置 ext4 状态/备份目录及既有测试根后：

```bash
sudo python3 -m scripts.register_target --initialize \
  --name test-root --mount-point /mnt/test-ext4 --relative-root CrossDisk_Test \
  --state-root /safe-external/state --backup-root /safe-external/backup \
  --allow-uid 1000 --allow-gid 1000 \
  --confirm-test-root /mnt/test-ext4/CrossDisk_Test --confirm-uuid 实际UUID

sudo python3 -m scripts.apply_bundle --bundle /path/to/bundle --target test-root --dry-run
```

以上 `/safe-external` 为示例路径，不能直接照抄为实际存储。无模式参数也只做预检。返回码 0 表示本次预检匹配，1 为拒绝/冲突，非法命令参数返回 2。

## 技术依据及证据边界

- Linux openat2：https://man7.org/linux/man-pages/man2/openat2.2.html
- mountinfo：https://man7.org/linux/man-pages/man5/proc_pid_mountinfo.5.html
- inode flags：https://man7.org/linux/man-pages/man2/ioctl_iflags.2.html

本机 Windows 自动测试覆盖策略、挂载记录解析、身份变化拒绝、命令参数边界与接口不可用时拒绝。真实 openat2、挂载绑定、ext4 ioctl、私有存储同步及完整流程须由上述 Ubuntu 集成脚本实测，不能以 Windows 模拟测试替代。

本轮本机验证：完整回归 **229 passed, 1 skipped**（43.99 秒）；交付包逐文件 SHA-256、ZIP 校验、Python 3.10 语法解析、独立解压目录命令入口及 Windows 拒绝执行均通过。Ubuntu 集成结果尚未取得，当前不标记该阶段实机验收完成。

## Ubuntu 报告复核补充（2026-11-06）

已收到并核对 CrossDisk_Preflight_Result_4658025a706f.zip，CRC 正常；14 个用例全部通过，每项 target_unchanged=true；正常与重复预检为 PREFLIGHT_OK，其余负向测试均拒绝。报告记录卸载后 e2fsck 检查通过。此前用户口头确认现已补充结果包证据。本次仅复核报告，未重新挂载或运行 Linux 测试。该包属于预检阶段，不是进程中断恢复实验结果。
