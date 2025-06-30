# Copyright 2022 Scott K Logan
# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from asyncio import Lock
from collections import defaultdict
import re
import subprocess
import sys

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_core.subprocess import run
from colcon_ros_buildfarm.local_repository import LocalRepositoryExtensionPoint

logger = colcon_logger.getChild(__name__)


class LocalRpmRepositoryExtension(LocalRepositoryExtensionPoint):
    """Import RPM packages into a repository residing on disk."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            LocalRepositoryExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')
        self._lock = defaultdict(Lock)
        self._pkg_match = re.compile(
            r'(.+)-(\d+(?:\.\d+)*)-(\d+.*)\.([^\.]+)\.rpm')

    def initialize(  # noqa: D102
        self, base_path, os_name, os_code_name, arch
    ):
        srpms_dir = base_path / os_name / os_code_name / 'SRPMS'
        arch_dir = base_path / os_name / os_code_name / arch
        debug_dir = arch_dir / 'debug'

        for repo_dir in (srpms_dir, arch_dir, debug_dir):
            if (repo_dir / 'repodata' / 'repomd.xml').is_file():
                continue
            repo_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f'Initializing RPM metadata in {repo_dir}')
            subprocess.check_call([
                sys.executable, '-c',
                'import createrepo_c; createrepo_c.createrepo_c()',
                '--quiet', '--no-database', '--general-compress-type=gz',
                str(repo_dir)])

    async def import_source(  # noqa: D102
        self, base_path, os_name, os_code_name, artifact_path
    ):
        srpms_dir = base_path / os_name / os_code_name / 'SRPMS'
        srpms = set(artifact_path.glob('sourcepkg/*.src.rpm'))
        num_srpms = len(srpms)
        if num_srpms != 1:
            logger.warning(
                'Found unexpected number of source RPMs in '
                f'{artifact_path} ({num_srpms})')
        if srpms:
            await self._import_to(srpms_dir, srpms)

    async def import_binary(  # noqa: D102
        self, base_path, os_name, os_code_name, arch, artifact_path
    ):
        arch_dir = base_path / os_name / os_code_name / arch
        debug_dir = arch_dir / 'debug'

        srpms = set(artifact_path.glob('binarypkg/*.src.rpm'))
        debug_rpms = set(artifact_path.glob('binarypkg/*-debuginfo-*.rpm'))
        debug_rpms.update(artifact_path.glob('binarypkg/*-debugsource-*.rpm'))
        arch_rpms = set(artifact_path.glob('binarypkg/*.rpm'))
        arch_rpms.difference_update(srpms)
        arch_rpms.difference_update(debug_rpms)

        if arch_rpms:
            await self._import_to(arch_dir, arch_rpms)
        else:
            logger.warning(
                f'Found no arch RPMs to import from {artifact_path}')

        if debug_rpms:
            await self._import_to(debug_dir, debug_rpms)

    async def _import_to(self, repo_dir, rpms):
        async with self._lock[repo_dir]:
            await self._import_to_no_lock(repo_dir, rpms)

    async def _import_to_no_lock(self, repo_dir, rpms):
        logger.debug(
            'Importing the following RPMs into {}: {}'.format(
                repo_dir, ', '.join(rpm.name for rpm in rpms)))

        names = set()
        for rpm in rpms:
            m = self._pkg_match.match(rpm.name)
            if not m:
                logger.warning(f'Failed to parse package name: {rpm.name}')
                continue
            names.add(m.group(1))

        for in_repo in repo_dir.rglob('*.rpm'):
            m = self._pkg_match.match(in_repo.name)
            if m and m.group(1) in names:
                in_repo.unlink()

        for rpm in rpms:
            in_repo = repo_dir / 'Packages' / rpm.name[0] / rpm.name
            in_repo.parent.mkdir(parents=True, exist_ok=True)
            in_repo.hardlink_to(rpm)

        # Rather than looking for createrepo_c on the path, we should invoke it
        # through the Python package we depend on, which may come with an
        # executable which isn't on the path.
        args = [
            sys.executable, '-c',
            'import createrepo_c; createrepo_c.createrepo_c()',
            '--quiet', '--no-database', '--update',
            '--general-compress-type=gz', str(repo_dir),
        ]
        res = await run(args, None, None)
        res.check_returncode()
