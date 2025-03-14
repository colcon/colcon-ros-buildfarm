# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from asyncio import Lock
from collections import defaultdict
import datetime
import gzip
import hashlib
import shutil

from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import run as colcon_core_subprocess_run
from colcon_ros_buildfarm.local_repository import LocalRepositoryExtensionPoint


class _RawAndGzFiles:

    def __init__(self, path):
        self._path = path
        self._raw = None
        self._com = None

    def write(self, data):
        self._raw.write(data)
        self._com.write(data)

    def __enter__(self):
        self._raw = self._path.open('wb')
        self._com = gzip.open(str(self._path) + '.gz', 'wb')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._raw.close()
        self._raw = None
        self._com.close()
        self._com = None


def _copy_to_pool(pool_dir, path):
    assert '_' in path.name
    name = path.name.split('_', 1)[0]
    subdir = pool_dir / name[0] / name
    subdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(path), str(subdir))


def _generate_release(os_dir, os_code_name):
    dist_dir = os_dir / 'dists' / os_code_name
    now = datetime.datetime.now(datetime.timezone.utc).strftime(
        '%a, %d %b %Y %H:%M:%S %Z')
    package_files = sorted(
        list(dist_dir.glob('main/*/Packages*')) +
        list(dist_dir.glob('main/source/Sources*')))
    with (dist_dir / 'Release').open('w') as release:
        release.write('Origin: ROS\n')
        release.write(f'Label: ROS {os_code_name}\n')
        release.write(f'Suite: {os_code_name}\n')
        release.write(f'Codename: {os_code_name}\n')
        release.write(f'Date: {now}\n')
        release.write('Architectures: amd64\n')
        release.write('Components: main\n')
        release.write(f'Description: ROS {os_code_name} Debian Repository\n')
        release.write('MD5Sum:\n')
        for package_file in package_files:
            with package_file.open('rb') as file:
                digest = hashlib.md5(file.read())
            release.write(f' {digest.hexdigest()}')
            release.write(f' {package_file.stat().st_size}')
            release.write(f' {package_file.relative_to(dist_dir)}\n')
        release.write('SHA1:\n')
        for package_file in package_files:
            with package_file.open('rb') as file:
                digest = hashlib.sha1(file.read())
            release.write(f' {digest.hexdigest()}')
            release.write(f' {package_file.stat().st_size}')
            release.write(f' {package_file.relative_to(dist_dir)}\n')
        release.write('SHA256:\n')
        for package_file in package_files:
            with package_file.open('rb') as file:
                digest = hashlib.sha256(file.read())
            release.write(f' {digest.hexdigest()}')
            release.write(f' {package_file.stat().st_size}')
            release.write(f' {package_file.relative_to(dist_dir)}\n')


class LocalDebRepositoryExtension(LocalRepositoryExtensionPoint):
    """Import deb packages into a repository residing on disk."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            LocalRepositoryExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._lock = defaultdict(Lock)
        self._dpkg_scanpackages = shutil.which('dpkg-scanpackages')
        if not self._dpkg_scanpackages:
            raise RuntimeError('Could not find dpkg-scanpackages')
        self._dpkg_scansources = shutil.which('dpkg-scansources')
        if not self._dpkg_scansources:
            raise RuntimeError('Could not find dpkg-scansources')

    def initialize(self, base_path, os_name, os_code_name, arch):  # noqa: D102
        os_dir = base_path / os_name
        dist_dir = os_dir / 'dists' / os_code_name
        force_update = False

        src_md_file = dist_dir / 'main' / 'source' / 'Sources'
        if not src_md_file.is_file():
            src_md_file.parent.mkdir(parents=True, exist_ok=True)
            src_md_file.touch()
            force_update = True
        src_md_gz_file = src_md_file.with_suffix(src_md_file.suffix + '.gz')
        if not src_md_gz_file.is_file():
            with src_md_file.open('r') as src_md:
                with src_md_gz_file.open('w') as src_md_gz:
                    shutil.copyfileobj(src_md, src_md_gz)
            force_update = True

        arch_md_file = dist_dir / 'main' / ('binary-' + arch) / 'Packages'
        if not arch_md_file.is_file():
            arch_md_file.parent.mkdir(parents=True, exist_ok=True)
            arch_md_file.touch()
            force_update = True
        arch_md_gz_file = arch_md_file.with_suffix(arch_md_file.suffix + '.gz')
        if not arch_md_gz_file.is_file():
            with arch_md_file.open('r') as arch_md:
                with arch_md_gz_file.open('w') as arch_md_gz:
                    shutil.copyfileobj(arch_md, arch_md_gz)
            force_update = True

        if not (dist_dir / 'Release').is_file() or force_update:
            _generate_release(os_dir, os_code_name)

    async def import_source(  # noqa: D102
        self, base_path, os_name, os_code_name, artifact_path
    ):
        os_dir = base_path / os_name

        async with self._lock[os_dir]:
            pool_dir = os_dir / 'pool'
            for deb in (artifact_path / 'sourcedeb').glob('*.dsc'):
                _copy_to_pool(pool_dir, deb)
            for deb in (artifact_path / 'sourcedeb').glob('*.orig.tar.gz'):
                _copy_to_pool(pool_dir, deb)
            for deb in (artifact_path / 'sourcedeb').glob('*.debian.tar.xz'):
                _copy_to_pool(pool_dir, deb)

            await self._update_metadata(os_dir, os_code_name)

    async def import_binary(  # noqa: D102
        self, base_path, os_name, os_code_name, arch, artifact_path
    ):
        os_dir = base_path / os_name

        async with self._lock[os_dir]:
            pool_dir = os_dir / 'pool'
            for deb in (artifact_path / 'binarydeb').glob('*.deb'):
                _copy_to_pool(pool_dir, deb)

            await self._update_metadata(os_dir, os_code_name, arch)

    async def _update_metadata(self, os_dir, os_code_name, arch=None):
        dist_dir = os_dir / 'dists' / os_code_name
        meta_dir = dist_dir / 'main' / ('binary-' + arch if arch else 'source')
        meta_dir.mkdir(parents=True, exist_ok=True)

        if arch is None:
            dpkg_args = [self._dpkg_scansources, 'pool/']
        else:
            dpkg_args = [self._dpkg_scanpackages, '--arch', arch, 'pool/']

        md_file = meta_dir / ('Packages' if arch else 'Sources')

        with _RawAndGzFiles(md_file) as md:
            dpkg_res = await colcon_core_subprocess_run(
                dpkg_args, stdout_callback=md.write,
                stderr_callback=None, cwd=str(os_dir))
        dpkg_res.check_returncode()

        _generate_release(os_dir, os_code_name)
