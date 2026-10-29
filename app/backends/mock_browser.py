"""纯内存演示数据；不调用真实文件系统、管理员或磁盘 API。"""

from app.core.browser import FileEntry, Location, Partition


class MockBrowserSource:
    def partitions(self) -> tuple[Partition, ...]:
        return (
            Partition("mock-c", "C: · Windows", "NTFS", "可读写", True, True, "模拟卷支持读写；全局安全模式仍为只读"),
            Partition("mock-d", "D: · 数据", "NTFS", "可读写", True, True, "模拟卷支持读写；全局安全模式仍为只读"),
            Partition("mock-ubuntu", "Ubuntu", "ext4", "只读", True, False, "ext4 未经过独立写入验证，仅允许只读"),
            Partition("mock-efi", "EFI", "FAT32", "受保护", False, False, "系统引导分区受保护，仅展示元数据"),
            Partition("mock-recovery", "Recovery", "NTFS", "受保护", False, False, "恢复分区受保护，仅展示元数据"),
            Partition("mock-msr", "MSR", "保留分区", "不可浏览", False, False, "MSR 没有普通文件树"),
            Partition("mock-admin", "权限演示卷", "ext4", "需要管理员", False, False, "当前无访问权限；演示模式不会请求提权"),
            Partition("mock-unknown", "未知演示卷", "未知", "不可识别", False, False, "文件系统不可识别，不可浏览"),
        )

    def list_directory(self, location: Location) -> tuple[FileEntry, ...]:
        partition = next((p for p in self.partitions() if p.id == location.partition_id), None)
        if partition is None or not partition.browsable:
            raise PermissionError("模拟分区不可访问")
        tree = {
            ("mock-c", ""): (FileEntry("用户文档", True), FileEntry("空目录", True),
                              FileEntry("中文长文件名示例_跨分区文件管理器使用说明.txt", False, 2048),
                              FileEntry(".演示隐藏文件", False, 16, hidden=True)),
            ("mock-c", "用户文档"): (FileEntry("项目资料", True), FileEntry("欢迎.txt", False, 120)),
            ("mock-c", "用户文档/项目资料"): (FileEntry("计划.md", False, 512),),
            ("mock-c", "空目录"): (),
            ("mock-d", ""): (FileEntry("空目录", True), FileEntry("演示图片.png", False, 8192)),
            ("mock-d", "空目录"): (),
            ("mock-ubuntu", ""): (FileEntry("home", True),),
            ("mock-ubuntu", "home"): (FileEntry("demo", True),),
            ("mock-ubuntu", "home/demo"): (FileEntry("只读说明.txt", False, 256),),
        }
        key = (location.partition_id, location.relative_path)
        if key not in tree:
            raise FileNotFoundError("模拟目录不存在，请选择列表中的目录")
        return tree[key]
