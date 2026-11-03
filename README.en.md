# CrossDisk Manager

[中文](README.md) | **English**

A cross-partition file manager for Windows 10/11 x64, built with Python, PySide6, and pytsk3. Browse, preview, search, and copy Windows files; make controlled changes inside explicitly authorized Windows data directories. Ubuntu ext4 access is currently read-only.

- **Version:** 1.0.0rc1, a V1.0 read-only-ext4 release candidate.
- **Author and copyright holder:** Jianchao Liu.
- **Project license:** [MIT](LICENSE). Third-party components retain their own licenses.
- **Application UI:** Simplified Chinese. An English README does not imply an English UI.

## Features and boundaries

| Feature | Current status |
|---|---|
| Disk, partition, and volume discovery | Read-only background queries; access roots are bound to partition context |
| Windows browsing | Paged listings, address bar, history, breadcrumbs, properties, and hidden files |
| Text, code, and image previews | Read-only, with byte/character/pixel limits; files are never executed |
| Filtering and searching | Filter loaded entries or explicitly start cross-partition metadata searches; cancel and locate results |
| Copying and exporting | Windows to Windows; verified ext4 `/home` data to Windows; no overwrite by default |
| Controlled Windows writes | Explicitly authorized directories on ordinary non-boot data volumes; create, save, rename, move within a volume, and delete files/empty directories |
| ext4 reading | Read-only pytsk3 backend with identity, range, and filesystem checks; insufficient device permissions cause an explicit failure |
| ext4 writing | **Disabled.** No actual write driver is integrated; configuration cannot enable it |
| Protected partitions | EFI, MSR, Recovery, and similar partitions expose limited metadata, without ordinary write operations |

The GUI does not elevate itself. Windows ACLs still control actual access. The application does not format disks, change partition tables, take disks offline, automatically mount Ubuntu, or bypass encryption and locks.

## Installation and startup

Requirements: Windows x64, Python **3.11 or 3.12**, and the Windows Storage PowerShell module. The currently verified local environment uses Python 3.12.8 and PySide6 6.10.0.

If this project's `.venv` already exists, use it directly rather than recreating it:

```powershell
cd D:\crossdisk_manager
.\.venv\Scripts\python.exe -m app.main
```

For a fresh setup, open ordinary PowerShell in your actual project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m app.main
```

If Python 3.12 is not registered with `py`, use the full path to its installed `python.exe` to create the environment. Activation and PowerShell execution-policy changes are unnecessary.

Demo mode uses simulated data without scanning real disks:

```powershell
.\.venv\Scripts\python.exe -m app.main --demo
```

## Basic workflow

1. Select an ordinary Windows volume after discovery. Browse using the address bar and breadcrumbs; select a file for a read-only preview.
2. Toolbar filters apply only to loaded entries. Start cross-partition searches explicitly. Errors and budget limits are reported as partial results.
3. Use **Copy/export to Windows** to copy into an existing Windows data directory. Existing directories are skipped as a whole by default; they are not merged or overwritten.
4. To change Windows files, select an ordinary non-boot data volume, choose **Configure Windows write directory**, select a directory, and confirm. Operations run in a separate window.
5. Editing supports UTF-8 text up to 2 MiB and saves UTF-8 without a BOM. Saves detect content conflicts and retain a `.bak` backup. Permanent deletion requires two confirmations; there is no general undo.
6. Read-only ext4 verification does not grant write access. There is no ext4 write switch. See the user guide for real Ubuntu access and permission limitations.

Cancelling a copy keeps completed files and cleans up only that job's unfinished temporary file. Cancellation and closing may wait for a blocked device call. Copies do not currently preserve timestamps or attributes.

## Configuration and logs

- Configuration: `%LOCALAPPDATA%\CrossDiskManager\config.json`.
- Rotating logs: `logs\app.log` under the same directory. The Help menu displays the last 64 KiB.
- `read_only=true` protects default browsing. A separate Windows write context requires explicit confirmation and never authorizes ext4 writes.
- No automatic file/log uploads or whole-disk background monitoring. Application logs omit file contents, tokens, and full sensitive paths.

## Tests and builds

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

The latest full regression on **2026-11-03** had **185 passed and 1 skipped**. The skip required Windows symbolic-link creation privileges. Dependency checks and the real disk inventory / GUI navigation startup check passed. See the [pre-upload validation record](docs/UPLOAD_2026-11-03.md) and [earlier repair record](docs/REPAIR_2026-10-31.md).

Build a Windows folder-based candidate from source:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m scripts.build_release
.\.venv\Scripts\python.exe -m scripts.smoke_frozen
.\.venv\Scripts\python.exe -m scripts.build_release --package-only
```

The build produces `dist/CrossDiskManager/CrossDiskManager.exe`, a ZIP, and a SHA-256 file. Keep the complete extracted folder, including `_internal`, notices, and documentation; do not copy the executable alone. Previous build outputs were cleaned up, so a ready-to-run executable is not currently guaranteed to accompany this checkout. This documentation update does not rebuild or publish binaries.

## Validation status

There is local Windows 11 startup evidence and Windows/synthetic-ext4-image regression coverage. **Full real-Ubuntu browsing/export, native Recycle Bin interaction and recovery, and independent Windows 10/other-machine validation remain pending.** Read-only image tests do not demonstrate ext4 write compatibility. This remains a release candidate.

## Documentation

The detailed documents below are currently in Chinese:

- [User guide](USER_GUIDE.md)
- [Security boundaries](SECURITY.md)
- [Support matrix](docs/SUPPORT_MATRIX.md)
- [ext4 write feasibility report](docs/EXT4_WRITE_FEASIBILITY.md)
- [Project progress](docs/PROGRESS.md)
- [Archived development history](docs/DEVELOPMENT_HISTORY.zh-CN.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## License

The project's own source code is licensed under the [MIT License](LICENSE). Copyright (c) 2026 **Jianchao Liu**. Dependencies, runtimes, and other third-party code remain subject to their original terms; this project's MIT license does not relicense them. Retain and comply with the applicable third-party notices and licenses when distributing builds.
