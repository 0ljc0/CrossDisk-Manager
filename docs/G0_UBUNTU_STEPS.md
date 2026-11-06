# Ubuntu G0 验证操作说明

本工具只创建自己的随机目录和 128 MiB 普通镜像，再通过专属 loop 设备挂载。不会接受真实分区或既有镜像作为格式化目标。不需要安装本项目或 pytsk3，Ubuntu Python 3.10 标准库即可。需要系统已有 e2fsprogs、util-linux。

## 1. 带入 Ubuntu

将交付包中的 g0_linux_prepare.py 复制到 Ubuntu 下载目录。重启进入 Ubuntu 后打开终端。以下假设脚本位于 ~/Downloads；中文系统请按实际下载目录调整。

## 2. 运行

```bash
sudo python3 ~/Downloads/g0_linux_prepare.py --output-parent /var/tmp
```

输出 READY (unmounted) 才表示全部完成。输出随机目录例如 /var/tmp/crossdisk-g0-abcdefgh。脚本创建普通样本、两种非零纳秒、整秒、两组所有者、不同权限、硬链接、中文名、空文件和 16 MiB 大文件；采集 Linux 真值，卸载后检查文件系统并绑定镜像 SHA-256。

执行失败时保留目录，不要继续对照或自行格式化任何设备。把完整终端错误交回分析。未出现 READY 时不要复制正在挂载的镜像。

## 3. 带回 Windows

READY 后将该目录中的 g0.img、truth.json、e2fsck.txt 复制到 Windows 能读的 U 盘或共享数据目录。目录是 root 私有的，可用 sudo cp 复制这三个文件到你已确认的介质挂载目录。复制完成后正常卸载移动介质。
不要手动修改 truth.json，也不要重新挂载或修改已经封存的 g0.img。

## 4. Windows 对照

回到 Windows，把三个文件放入 D:\crossdisk_manager\g0-results（自己新建该目录），然后运行：

```powershell
cd D:\crossdisk_manager
.\.venv\Scripts\python.exe -m scripts.g0_compare --image .\g0-results\g0.img --truth .\g0-results\truth.json
```

image_unchanged 为 true 且 differences 为空表示该报告内字段匹配。镜像哈希不符、文件系统检查非零或任一字段不符都会拒绝或返回失败。
这不是自动写入授权；还需审查样本覆盖和 Linux 证据，再决定 G0 是否通过。工具从未启用 ext4 写入。

## 验证边界

Windows 已验证比较器成功路径、镜像摘要不符拒绝及 Linux 工具在 Windows 拒绝运行。Ubuntu 实际挂载、纳秒真值及 e2fsck 流程尚待你在 Ubuntu 运行；不能把 Windows 单元测试视为 Linux 验收。
