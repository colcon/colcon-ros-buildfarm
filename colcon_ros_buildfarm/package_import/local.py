# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import argparse
import os
from pathlib import Path

from colcon_core.argument_default import wrap_default_value
from colcon_core.event_handler import EventHandlerExtensionPoint
from colcon_core.event_reactor import EventReactorShutdown
from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import satisfies_version
from colcon_ros_buildfarm.config_augmentation \
    import ConfigAugmentationExtensionPoint
from colcon_ros_buildfarm.file_server import SimpleFileServer
from colcon_ros_buildfarm.local_repository \
    import select_local_repository_extension
from colcon_ros_buildfarm.package_import import PackageImportExtensionPoint
import yaml

logger = colcon_logger.getChild(__name__)


class LocalPackageImportExtension(
    ConfigAugmentationExtensionPoint,
    EventHandlerExtensionPoint,
    PackageImportExtensionPoint,
):
    """Import packages into a repository residing on disk."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            ConfigAugmentationExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        satisfies_version(
            EventHandlerExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        satisfies_version(
            PackageImportExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._server = None

    def _set_up_server(self, repo_base, target_platforms, port):
        for os_name, os_code_name, arch in target_platforms:
            extension = select_local_repository_extension(os_name)
            if extension is None:
                raise RuntimeError(f'No local repo support for {os_name}')
            extension.initialize(repo_base, os_name, os_code_name, arch)

        self._server = SimpleFileServer(str(repo_base))
        host, port = self._server.start(port=port)

        return host, port

    def augment_config(self, index_path, args):  # noqa: D102
        if (
            getattr(args, 'package_import', None) != 'local' or
            getattr(args, 'build_name', None) is None or
            getattr(args, 'ros_distro', None) is None
        ):
            return

        with index_path.open('r') as f:
            index_data = yaml.safe_load(f)

        distro_data = index_data['distributions'][args.ros_distro]
        build_file_name = distro_data['release_builds'][args.build_name]
        build_file_path = index_path.parent / build_file_name

        with build_file_path.open('r') as f:
            build_file_data = yaml.safe_load(f)

        targets = []
        for os_name, target in build_file_data['targets'].items():
            for os_code_name, arches in target.items():
                for arch in arches:
                    targets.append((os_name, os_code_name, arch))
            break
        else:
            # This appears to be a general limitation of ros_buildfarm
            # build files
            assert False, 'A build file can only support a single OS'

        repositories = build_file_data.setdefault('repositories', {})
        repo_keys = repositories.setdefault('keys', [])
        repo_urls = repositories.setdefault('urls', [])

        repo_keys.insert(0, '')

        host, port = self._set_up_server(
            Path(args.repo_base), targets, args.repo_server_port)
        repo_url = f'http://{host}:{port}/{os_name}'
        if os_name in ('fedora', 'rhel'):
            repo_urls.insert(0, repo_url + '/$releasever/$basearch')
        else:
            repo_urls.insert(0, repo_url)
        build_file_data['target_repository'] = repo_url

        with build_file_path.open('w') as f:
            yaml.dump(build_file_data, f)

    def __call__(self, event):  # noqa: D102
        if isinstance(event[0], EventReactorShutdown) and self._server:
            self._server.stop()
            self._server = None

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--repo-base',
            default=wrap_default_value('repo'),
            help='The base path for locally importing built packages '
                 '(default: repo)')
        parser.add_argument(
            '--repo-server-port',
            type=int, default=0,
            help=argparse.SUPPRESS)

    async def import_source(  # noqa: D102
        self, args, os_name, os_code_name, artifact_path
    ):
        repo_base = Path(os.path.abspath(args.repo_base))
        extension = select_local_repository_extension(os_name)
        if not extension:
            logger.warn(
                'No local package repository extension found to import source '
                "package for OS '{os_name}'".format_map(locals()))
            return
        return await extension.import_source(repo_base, os_name,
                                             os_code_name, artifact_path)

    async def import_binary(  # noqa: D102
        self, args, os_name, os_code_name, arch, artifact_path
    ):
        repo_base = Path(os.path.abspath(args.repo_base))
        extension = select_local_repository_extension(os_name)
        if not extension:
            logger.warn(
                'No local package repository extension found to import binary '
                "package for OS '{os_name}'".format_map(locals()))
            return
        return await extension.import_binary(repo_base, os_name, os_code_name,
                                             arch, artifact_path)
