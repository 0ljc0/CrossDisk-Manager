"""本地可复现构建与许可证归档，不上传或签名发布。"""
import importlib.metadata as metadata
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from app.core.version import VERSION


def main():
    root = Path(__file__).resolve().parents[1]
    # 宿主 PATH 可能含其他 Python/图像库，禁止误收集其旧 UCRT DLL。
    windows = Path(os.environ['SystemRoot'])
    build_env = dict(os.environ, PATH=os.pathsep.join(map(str, (Path(sys.executable).parent,
        Path(sys.base_prefix), windows / 'System32', windows))))
    if '--package-only' not in sys.argv[1:]:
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(root / 'CrossDiskManager.spec')],
                       cwd=root, env=build_env, check=True)
    output = root / 'dist/CrossDiskManager'
    for name in ('README.md', 'README.en.md', 'LICENSE', 'USER_GUIDE.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(root / name, output / name)
    shutil.copytree(root / 'docs', output / 'docs', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('screenshots', 'tasks'))
    licenses = output / 'third_party'
    licenses.mkdir(exist_ok=True)
    components = []
    for name in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pytsk3', 'pyinstaller'):
        distribution = metadata.distribution(name)
        folder = licenses / name
        folder.mkdir(exist_ok=True)
        (folder / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
        count = 0
        for file in distribution.files or ():
            if 'licenses' in file.parts or file.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = folder / Path(*file.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    count += 1
        if not count:
            raise RuntimeError('依赖缺少许可文本：' + name)
        components.append(dict(name=name, version=distribution.version, license_files=count))
    shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', licenses / 'Python-LICENSE.txt')
    shutil.copytree(root / 'packaging/qt-licenses', licenses / 'Qt-open-source', dirs_exist_ok=True)
    manifest = dict(version=VERSION, python=sys.version.split()[0], components=components,
                    executable_sha256=hashlib.sha256((output / 'CrossDiskManager.exe').read_bytes()).hexdigest())
    (output / 'BUILD_MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    archive = root / f'dist/CrossDiskManager-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as writer:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                writer.write(path, path.relative_to(output.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps(dict(archive=archive.name, sha256=digest, bytes=archive.stat().st_size), indent=2))


if __name__ == '__main__':
    main()
