# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from colcon_core.dependency_descriptor import DependencyDescriptor
from colcon_core.package_augmentation \
    import PackageAugmentationExtensionPoint
from colcon_core.plugin_system import satisfies_version


class RosWorkspacePackageAugmentation(PackageAugmentationExtensionPoint):
    """
    Augment packages to include a dependency on the ``ros_workspace`` package.

    Packages which are dependencies of the ``ros_workspace`` package are not
    modified.
    """

    # the priority needs to be lower than augmentation extensions which
    # read the dependencies
    PRIORITY = 50

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(
            PackageAugmentationExtensionPoint.EXTENSION_POINT_VERSION,
            '^1.0')

    def augment_packages(  # noqa: D102
        self, descs, *, additional_argument_names=None
    ):
        ros_workspace = next(
            iter(d for d in descs if d.name == 'ros_workspace'), None)
        if ros_workspace is None or ros_workspace.type != 'ros_distro':
            return

        to_exclude = ros_workspace.get_recursive_dependencies(
            descs, ('build', 'test'), ('run',))
        to_exclude.add('ros_workspace')

        metadata = {
            'origin': 'ros_workspace',
        }

        for desc in descs:
            if desc.type != 'ros_distro' or desc.name in to_exclude:
                continue
            desc.dependencies['build'].add(DependencyDescriptor(
                'ros_workspace', metadata=metadata))
            desc.dependencies['run'].add(DependencyDescriptor(
                'ros_workspace', metadata=metadata))
