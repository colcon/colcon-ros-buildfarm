# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

import os
import traceback
from urllib.parse import urlparse

from colcon_core.logging import colcon_logger
from colcon_core.plugin_system import instantiate_extensions
from colcon_core.plugin_system import order_extensions_by_priority
from ros_buildfarm.config import load_yaml
import yaml

logger = colcon_logger.getChild(__name__)


class ConfigAugmentationExtensionPoint:
    """
    The interface for augmenting the ROS buildfarm configuration.

    After fetching the upstream configuration, these extensions are responsible
    for making the necessary changes to that configuration to facilitate local
    builds.
    """

    """The version of the config augmentation extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    """The default priority of config augmentation extensions."""
    PRIORITY = 100

    def augment_config(self, index_path, args):
        """
        Augment the ROS buildfarm configuration files.

        :param index_path: The path to the configuration index file.
        :param args: The parsed command line arguments
        """
        raise NotImplementedError()


def get_config_augmentation_extensions(*, group_name=None):
    """
    Get the available config augmentation extensions.

    The extensions are ordered by their priority and entry point name.

    :rtype: OrderedDict
    """
    if group_name is None:
        group_name = __name__
    extensions = instantiate_extensions(group_name)
    for name, extension in extensions.items():
        extension.CONFIG_AUGMENTATION_NAME = name
    return order_extensions_by_priority(extensions)


def augment_config(index_path, args, *, augmentation_extensions=None):
    """
    Augment the ROS buildfarm configuration.

    :param index_path: The path to the configuration index file.
    """
    if augmentation_extensions is None:
        augmentation_extensions = get_config_augmentation_extensions()

    for extension in augmentation_extensions.values():
        try:
            retval = extension.augment_config(index_path, args)
            assert retval is None, 'augment_config() should return None'
        except Exception as e:  # noqa: F841
            # catch exceptions raised in augmentation extension
            exc = traceback.format_exc()
            logger.error(
                'Exception in config augmentation extension '
                "'{extension.CONFIG_AUGMENTATION_NAME}': "
                '{e}\n{exc}'.format_map(locals()))
            # skip failing extension, continue with next one


def get_config(
    config_path, ros_distro, release_name, *, args, upstream_config_url
):
    """
    Fetch and augment the upstream buildfarm configuration.

    :param config_path: Local directory where the augmented configuration
      should be stored.
    :param ros_distro: Name of the ROS distribution.
    :param release_name: The release build name in the upstream buildfarm
      configuration index.
    :param args: Arguments to pass to configuration augmentation extensions
    :param upstream_config_url: URL to the upstream buildfarm configuration
      index.

    :returns: URL to the augmented buildfarm configuration index.
    """
    config_path.mkdir(parents=True, exist_ok=True)
    upstream_base_url = os.path.dirname(upstream_config_url)
    index_name = os.path.basename(upstream_config_url)

    # Fetch the index
    index_path = config_path / index_name
    index_data = load_yaml(upstream_config_url)

    # Fetch the release configuration
    ros_distro_data = index_data['distributions'][ros_distro]
    build_file_data = load_yaml(_resolve_url(
        upstream_base_url,
        ros_distro_data['release_builds'][release_name]))

    # Drop irrelevant release build files
    for other_release_name in tuple(ros_distro_data['release_builds'].keys()):
        if other_release_name != release_name:
            del ros_distro_data['release_builds'][other_release_name]

    # Write out the index
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open('w') as f:
        yaml.dump(index_data, f)

    # Write out the release build file
    build_file_path = (
        config_path / ros_distro_data['release_builds'][release_name])
    build_file_path.parent.mkdir(parents=True, exist_ok=True)
    with build_file_path.open('w') as f:
        yaml.dump(build_file_data, f)

    augment_config(index_path, args)

    return index_path.resolve().as_uri()


def _resolve_url(base_url, value):
    parts = urlparse(value)
    if not parts[0]:  # schema
        value = base_url + '/' + value
    return value
