"""Verify and install the Git LFS-backed Windows land-recognition distribution."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'integrations/huiyan-land/artifacts'
DESTINATION = ROOT / 'var/huiyan-land'
EXPECTED_DIRECTORY = '方舟慧眼-轻量版'


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def install():
    if sys.platform != 'win32':
        raise SystemExit('该发行包仅支持 Windows；Linux 需要原项目源码或 Linux 发行包。')
    manifest = json.loads((ARTIFACTS / 'manifest.json').read_text(encoding='utf-8'))
    target = DESTINATION / EXPECTED_DIRECTORY
    if target.exists():
        raise SystemExit(f'安装目录已存在，请先自行备份或使用现有安装：{target}')
    DESTINATION.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='huiyan-install-', dir=DESTINATION) as temporary:
        temp = Path(temporary)
        archive = temp / 'distribution.zip'
        total = hashlib.sha256()
        with archive.open('wb') as output:
            for item in manifest['parts']:
                name = item['name']
                if Path(name).name != name:
                    raise SystemExit('分卷文件名无效。')
                part = ARTIFACTS / name
                if not part.is_file() or part.stat().st_size != item['size'] or digest(part) != item['sha256']:
                    raise SystemExit(f'分卷缺失或校验失败：{name}。请先执行 git lfs pull。')
                with part.open('rb') as source:
                    for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
                        total.update(block)
                        output.write(block)
        if total.hexdigest() != manifest['archive_sha256']:
            raise SystemExit('安装包整体校验失败。')
        extraction = temp / 'unpacked'
        extraction.mkdir()
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                path = PurePosixPath(info.filename.replace('\\', '/'))
                if (path.is_absolute() or not path.parts or path.parts[0] != EXPECTED_DIRECTORY or
                    any(part in ('..', '') or ':' in part for part in path.parts) or
                    (info.external_attr >> 16) & 0o170000 == 0o120000):
                    raise SystemExit('安装包包含不安全的文件路径。')
            package.extractall(extraction)
        source = extraction / EXPECTED_DIRECTORY
        if not (source / '方舟慧眼-轻量版.exe').is_file() or not (source / 'checkpoints').is_dir():
            raise SystemExit('安装包缺少程序或模型。')
        shutil.move(str(source), str(target))
    print(f'识物程序已安装到 {target}；重启 Django 后会自动使用。')


if __name__ == '__main__':
    install()
