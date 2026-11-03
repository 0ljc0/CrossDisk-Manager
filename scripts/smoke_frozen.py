"""打包产物黑盒验收：不同工作目录、真实GUI、Windows/ext4镜像后台。"""
from dataclasses import asdict
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from app.core.search import SearchLimits, SearchQuery
from app.backends.ext4_readonly import Ext4ReadOnlyBackend


def main():
    root = Path(__file__).resolve().parents[1]
    executable = root / 'dist/CrossDiskManager/CrossDiskManager.exe'
    sys.path.insert(0, str(root / 'tests'))
    from ext4_fixture import make_image
    from test_inventory import sample, parse
    from test_search import native_source
    report = dict(platform=sys.platform, administrator=bool(ctypes.windll.shell32.IsUserAnAdmin()), checks=[])
    with tempfile.TemporaryDirectory(prefix='CrossDisk-发布验收-') as temporary:
        directory = Path(temporary)
        env = dict(os.environ, LOCALAPPDATA=str(directory / 'user-data'))
        def invoke(arguments, payload=None):
            result = subprocess.run([str(executable), *arguments], input=json.dumps(payload) if payload is not None else None,
                capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=directory, env=env, timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            assert result.returncode == 0, (arguments, result.returncode, (result.stderr or '')[-1000:])
            return result.stdout
        files = directory / '中文 files'
        files.mkdir()
        (files / 'sample.py').write_text("# frozen validation\n", encoding='utf-8')
        native = dict(native_source(files), show_hidden=True, offset=0, fingerprint='')
        result = json.loads(invoke(['--worker', 'native'], native))
        assert result['page']['entries'][0]['name'] == 'sample.py'
        report['checks'].append('native-directory')
        preview = dict(native, task='preview', relative_path='sample.py', byte_limit=2*1024*1024, encoding='auto')
        assert json.loads(invoke(['--worker', 'native'], preview))['preview']['text'] == '# frozen validation\n'
        report['checks'].append('native-preview')
        image = make_image(directory / 'image.ext4', include_python=True)
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        inventory = parse(sample.__wrapped__())
        partition, disk = inventory.partitions[5], inventory.disks[0]
        with Ext4ReadOnlyBackend.from_image(str(image)) as backend:
            fingerprint = backend.probe['fingerprint']
        ext4 = dict(partition_id=partition.id, partition_name='镜像', root='', relative_path='home', show_hidden=True,
                    offset=0, fingerprint='', backend_spec=dict(kind='ext4', image=str(image), fingerprint=fingerprint,
                    partition=asdict(partition), disk=asdict(disk)))
        assert json.loads(invoke(['--worker', 'native'], ext4))['page']['entries'][0]['name'] == 'demo'
        report['checks'].append('ext4-image-directory')
        preview = dict(ext4, task='preview', relative_path='home/demo/script.py', byte_limit=2*1024*1024, encoding='auto')
        assert "image only" in json.loads(invoke(['--worker', 'native'], preview))['preview']['text']
        report['checks'].append('ext4-image-preview')
        events = [json.loads(line) for line in invoke(['--worker', 'search'],
            dict(sources=[native, ext4], query=asdict(SearchQuery('*.py')), limits=asdict(SearchLimits()))).splitlines()]
        assert events[-1]['stats']['complete'] and events[-1]['stats']['matches'] == 2
        report['checks'].append('cross-backend-search')
        invoke(['--demo', '--smoke-test'])
        report['checks'].append('gui-demo')
        invoke(['--smoke-test'])
        report['checks'].append('gui-real-inventory-and-navigation')
        assert digest == hashlib.sha256(image.read_bytes()).hexdigest()
        report['checks'].append('image-sha256-unchanged')
        report['executable_sha256'] = hashlib.sha256(executable.read_bytes()).hexdigest()
    target = root / 'docs/TASK12_FROZEN_SMOKE.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
