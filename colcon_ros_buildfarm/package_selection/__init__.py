# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from colcon_core.package_selection import add_arguments as _add_arguments
from colcon_core.package_selection import get_package_selection_extensions \
    as _get_package_selection_extensions
from colcon_core.package_selection import get_packages as _get_packages
from colcon_ros_buildfarm.package_augmentation \
    import get_package_augmentation_extensions
from colcon_ros_buildfarm.package_discovery \
    import get_package_discovery_extensions


def add_arguments(*args, **kwargs):
    """
    Add the command line arguments for the package selection extensions.

    The function will call :function:`add_package_discovery_arguments` to add
    the package discovery arguments.

    :param parser: The argument parser
    """
    if kwargs.get('discovery_extensions') is None:
        kwargs['discovery_extensions'] = get_package_discovery_extensions()
    if kwargs.get('selection_extensions') is None:
        kwargs['selection_extensions'] = get_package_selection_extensions()

    _add_arguments(*args, **kwargs)


def get_package_selection_extensions(*args, **kwargs):
    """
    Get the available package selection extensions.

    The extensions are ordered by their entry point name.

    :rtype: OrderedDict
    """
    if kwargs.get('group_name') is None:
        kwargs['group_name'] = __name__
    return _get_package_selection_extensions(*args, **kwargs)


def get_packages(*args, **kwargs):
    """
    Get the selected package decorators in topological order.

    The overview of the process:
    * Get the package descriptors
    * Order them topologically
    * Select the packages based on the command line arguments

    :param additional_argument_names: A list of additional arguments to
      consider
    :param Iterable[str] direct_categories: The names of the direct categories
    :param Iterable[str]|Mapping[str, Iterable[str]] recursive_categories:
      The names of the recursive categories, optionally mapped from the
      immediate upstream category which included the dependency
    :rtype: list
    :raises RuntimeError: if the returned set of packages contains duplicates
      package names
    """
    if kwargs.get('discovery_extensions') is None:
        kwargs['discovery_extensions'] = get_package_discovery_extensions()
    kwargs['identification_extensions'] = {}
    if kwargs.get('augmentation_extensions') is None:
        kwargs['augmentation_extensions'] = \
            get_package_augmentation_extensions()
    if kwargs.get('selection_extensions') is None:
        kwargs['selection_extensions'] = get_package_selection_extensions()

    return _get_packages(*args, **kwargs)
