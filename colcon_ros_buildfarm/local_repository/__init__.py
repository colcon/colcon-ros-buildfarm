# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from colcon_core.plugin_system import instantiate_extensions
from ros_buildfarm.common import package_format_mapping


class LocalRepositoryExtensionPoint:
    """
    The interface for 'local' package repository import.

    Each extension is expected to handle a specific package format.
    """

    """The version of the local repository import extension interface."""
    EXTENSION_POINT_VERSION = '1.0'

    def initialize(self, base_path, os_name, os_code_name, arch):
        """
        Initialize the local repository metadata (if necessary).

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param arch: The system architecture the package was built for
        """
        pass

    async def import_source(
        self, base_path, os_name, os_code_name, artifact_path
    ):
        """
        Import a source package into the local repository.

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()

    async def import_binary(
        self, base_path, os_name, os_code_name, arch, artifact_path
    ):
        """
        Import a binary package into the repository.

        :param base_path: The base path of the repository to import into
        :param os_name: The name of the operating system the package was built
          for
        :param os_code_name: The code name or version of the operating system
          the package was built for
        :param arch: The system architecture the package was built for
        :param artifact_path: The path to the package artifact(s) to be
          imported
        """
        raise NotImplementedError()


def get_local_repository_extensions(*, group_name=None):
    """
    Get the available local package repository extensions.

    :rtype: dict
    """
    if group_name is None:
        group_name = __name__
    return instantiate_extensions(group_name)


def select_local_repository_extension(os_name, *, extensions=None):
    """
    Get the available local package repository extension.

    :param os_name: The operating system to import the package for

    :returns: The local repository extension, or 'None' if not supported
    """
    package_format = package_format_mapping.get(os_name)
    if extensions is None:
        extensions = get_local_repository_extensions()
    return extensions.get(package_format)
