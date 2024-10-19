# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from tempfile import TemporaryDirectory

from colcon_core.package_selection import PackageSelectionExtensionPoint
from colcon_core.plugin_system import satisfies_version
from colcon_ros_buildfarm.config_augmentation \
    import ConfigAugmentationExtensionPoint
from ros_buildfarm.common import get_os_package_name
from ros_buildfarm.common import Target
from ros_buildfarm.config import get_index
from ros_buildfarm.config import get_release_build_files
from ros_buildfarm.package_repo import get_package_repo_data


def _get_packages_in_repo(index_url, ros_distro, release_name):
    config = get_index(index_url)
    build_files = get_release_build_files(config, ros_distro)
    build_file = build_files[release_name]

    targets = []
    for os_name, os_code_names in build_file.targets.items():
        for os_code_name, arches in os_code_names.items():
            for arch in arches:
                targets.append(Target(os_name, os_code_name, arch))

    with TemporaryDirectory() as temp:
        repo_data = get_package_repo_data(
            build_file.target_repository, targets, temp)

    assert len(targets) == 1, 'Only a single target is supported'
    target = next(iter(targets))

    return set(repo_data[target].keys())


class MissingFromRepoPackageSelection(
    PackageSelectionExtensionPoint,
    ConfigAugmentationExtensionPoint,
):
    """Select packages which are missing from the target repository."""

    PRIORITY = 10

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            PackageSelectionExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        satisfies_version(
            ConfigAugmentationExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')
        self._in_repo = None

    def add_arguments(self, *, parser):  # noqa: D102
        parser.add_argument(
            '--packages-select-missing-from-repo', action='store_true',
            help='Only process a subset of packages which are not currently '
                 'present in the buildfarm target repository')

    def augment_config(self, index_path, args):  # noqa: D102
        if not getattr(args, 'packages_select_missing_from_repo', False):
            return

        index_url = index_path.resolve().as_uri()
        self._in_repo = _get_packages_in_repo(
            index_url, args.ros_distro, args.build_name)

    def select_packages(self, args, decorators):  # noqa: D102
        if not self._in_repo:
            return

        for decorator in decorators:
            pkg_name = get_os_package_name(
                args.ros_distro, decorator.descriptor.name)
            if pkg_name in self._in_repo:
                decorator.selected = False
