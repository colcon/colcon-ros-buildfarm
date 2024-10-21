# Copyright 2022 Scott K Logan
# Copyright 2016-2018 Dirk Thomas
# Licensed under the Apache License, Version 2.0

from collections import OrderedDict
import logging
import os
from pathlib import Path

from colcon_core.argument_default import wrap_default_value
from colcon_core.argument_parser.destination_collector \
    import DestinationCollectorDecorator
from colcon_core.event_handler import add_event_handler_arguments
from colcon_core.executor import add_executor_arguments
from colcon_core.executor import execute_jobs
from colcon_core.executor import Job
from colcon_core.executor import OnError
from colcon_core.logging import colcon_logger
from colcon_core.logging import get_effective_console_level
from colcon_core.package_identification.ignore import IGNORE_MARKER
from colcon_core.plugin_system import satisfies_version
from colcon_core.task import add_task_arguments
from colcon_core.task import get_task_extension
from colcon_core.task import TaskContext
from colcon_core.verb import check_and_mark_build_tool
from colcon_core.verb import logger
from colcon_core.verb import update_object
from colcon_core.verb import VerbExtensionPoint
from colcon_ros_buildfarm.config_augmentation \
    import get_config
from colcon_ros_buildfarm.package_import \
    import add_package_import_arguments
from colcon_ros_buildfarm.package_selection \
    import add_arguments as add_packages_arguments
from colcon_ros_buildfarm.package_selection import get_packages
from ros_buildfarm.config import get_index
from ros_buildfarm.config import get_release_build_files


DEFAULT_CONFIG_URL = 'https://raw.githubusercontent.com' \
    '/ros2/ros_buildfarm_config/ros2/index.yaml'


class ReleaseJobArguments:
    """Arguments to build a specific ROS buildfarm release job."""

    def __init__(
        self, pkg, args, os_name, os_code_name, arch=None, *,
        additional_destinations=None,
    ):
        """
        Construct a ReleaseJobArguments.

        :param pkg: The package descriptor
        :param args: The parsed command line arguments
        :param os_name: The name of the target OS
        :param os_code_name: The code name of the release of the target OS
        :param arch: The architecture of the target OS
        :param list additional_destinations: The destinations of additional
          arguments
        """
        self.arch = arch
        self.build_base = os.path.abspath(os.path.join(
            os.getcwd(), args.build_base, pkg.name))
        self.build_name = args.build_name
        self.config_url = args.config_url
        self.os_code_name = os_code_name
        self.os_name = os_name

        # set additional arguments
        for dest in (additional_destinations or []):
            # from the command line
            if hasattr(args, dest):
                update_object(
                    self, dest, getattr(args, dest),
                    pkg.name, 'release', 'command line')
            # from the package metadata
            if dest in pkg.metadata:
                update_object(
                    self, dest, pkg.metadata[dest],
                    pkg.name, 'release', 'package metadata')


def platform_argument(value):
    """Parse a string containing a colcon-separated platform argument."""
    if value.count(':') != 2:
        raise ValueError('Platform must contain three colcon-separated values')
    return tuple(value.split(':', 2))


def _get_targets(config, ros_distro, release_name):
    build_files = get_release_build_files(config, ros_distro)
    build_file = build_files[release_name]

    targets = []
    for os_name, os_code_names in build_file.targets.items():
        for os_code_name, arches in os_code_names.items():
            for arch in arches:
                targets.append((os_name, os_code_name, arch))
    return targets


def _get_source_job_id(pkg_name, ros_distro, args):
    ros_distro_prefix = ros_distro[0].upper()
    prefix = f'{ros_distro_prefix}src'
    if args.build_name != 'default':
        prefix += f'_{args.build_name}'

    return f'{prefix}__{pkg_name}__' \
        f'{args.os_name}_{args.os_code_name}'


def _get_binary_job_id(pkg_name, ros_distro, args):
    ros_distro_prefix = ros_distro[0].upper()
    prefix = f'{ros_distro_prefix}rel'
    if args.build_name != 'default':
        prefix += f'_{args.build_name}'

    return f'{prefix}__{pkg_name}__' \
        f'{args.os_name}_{args.os_code_name}_{args.arch}'


class RosBuildfarmReleaseVerb(VerbExtensionPoint):
    """Build release packages using the ROS buildfarm."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(VerbExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--build-base',
            default=wrap_default_value('buildfarm'),
            help='The base path for all build directories '
                 '(default: buildfarm)')
        parser.add_argument(
            '--continue-on-error',
            action='store_true',
            help='Continue other packages when a package fails to build '
                 '(packages recursively depending on the failed package are '
                 'skipped)')

        parser.add_argument(
            '--build-name',
            default='default')
        parser.add_argument(
            '--config-url',
            default=DEFAULT_CONFIG_URL)
        parser.add_argument(
            '--target-platform',
            metavar='OS:VERSION:ARCH',
            type=platform_argument,
            nargs='*')

        add_executor_arguments(parser)
        add_event_handler_arguments(parser)

        add_packages_arguments(parser)

        decorated_parser = DestinationCollectorDecorator(parser)
        add_task_arguments(
            decorated_parser, 'colcon_ros_buildfarm.task.release')
        add_package_import_arguments(decorated_parser)
        self.extra_argument_destinations = decorated_parser.get_destinations()

    def main(self, *, context):  # noqa: D102
        log_level = get_effective_console_level(colcon_logger)
        logging.getLogger('ros_buildfarm').setLevel(log_level)

        check_and_mark_build_tool(context.args.build_base)

        self._create_path(context.args.build_base)

        config_path = Path(context.args.build_base) / '_buildfarm_config'
        augmented_config_url = get_config(
            config_path, context.args.ros_distro, context.args.build_name,
            args=context.args, upstream_config_url=context.args.config_url)
        context.args.config_url = augmented_config_url

        config = get_index(context.args.config_url)
        os.environ['ROSDISTRO_INDEX_URL'] = config.rosdistro_index_url
        if context.args.target_platform is None:
            context.args.target_platform = _get_targets(
                config, context.args.ros_distro, context.args.build_name)

        decorators = get_packages(
            context.args,
            additional_argument_names=self.extra_argument_destinations,
            recursive_categories=('run', ))

        jobs = self._get_jobs(context.args, decorators)

        on_error = OnError.interrupt \
            if not context.args.continue_on_error else OnError.skip_downstream

        return execute_jobs(context, jobs, on_error=on_error)

    def _create_path(self, path):
        path = Path(os.path.abspath(path))
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        ignore_marker = path / IGNORE_MARKER
        if not os.path.lexists(str(ignore_marker)):
            with ignore_marker.open('w'):
                pass

    def _get_jobs(self, args, decorators):
        jobs = OrderedDict()
        unselected_packages = set()
        additional_destinations = self.extra_argument_destinations.values()
        for decorator in decorators:
            pkg = decorator.descriptor
            ros_distro = str(pkg.path.parts[0])

            if not decorator.selected:
                unselected_packages.add(pkg)
                continue

            src_extension = get_task_extension(
                'colcon_ros_buildfarm.task.release',
                pkg.type + '.source')
            if not src_extension:
                logger.warning(
                    f"No task extension for job 'release' of a '{pkg.type}' "
                    'package')
                continue

            source_platforms = {plat[:2] for plat in args.target_platform}
            for os_name, os_code_name in source_platforms:
                job_args = ReleaseJobArguments(
                    pkg, args, os_name, os_code_name,
                    additional_destinations=additional_destinations)
                task_context = TaskContext(
                    pkg=pkg, args=job_args,
                    dependencies=OrderedDict())
                job = Job(
                    identifier=_get_source_job_id(
                        pkg.name, ros_distro, job_args),
                    dependencies={},
                    task=src_extension, task_context=task_context)

                jobs[job.identifier] = job

            bin_extension = get_task_extension(
                'colcon_ros_buildfarm.task.release',
                pkg.type + '.binary')
            if not bin_extension:
                logger.warning(
                    f"No task extension for job 'release' of a '{pkg.type}' "
                    'package')
                continue

            recursive_dependencies = OrderedDict()
            for dep_name in decorator.recursive_dependencies:
                recursive_dependencies[dep_name] = dep_name

            for os_name, os_code_name, arch in args.target_platform:
                job_args = ReleaseJobArguments(
                    pkg, args, os_name, os_code_name, arch,
                    additional_destinations=additional_destinations)
                task_context = TaskContext(
                    pkg=pkg, args=job_args,
                    dependencies=recursive_dependencies)

                dependency_identifiers = {
                    _get_source_job_id(pkg.name, ros_distro, job_args),
                }
                dependency_identifiers.update(
                    _get_binary_job_id(dep, ros_distro, job_args)
                    for dep in recursive_dependencies.keys())

                job = Job(
                    identifier=_get_binary_job_id(
                        pkg.name, ros_distro, job_args),
                    dependencies=dependency_identifiers,
                    task=bin_extension, task_context=task_context)

                jobs[job.identifier] = job

        return jobs
