# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from colcon_core.package_discovery \
    import get_package_discovery_extensions \
    as _get_package_discovery_extensions


def get_package_discovery_extensions(*args, **kwargs):
    """
    Get the available ROS buildfarm package discovery extensions.

    The extensions are ordered by their priority and entry point name.

    :rtype: OrderedDict
    """
    if kwargs.get('group_name') is None:
        kwargs['group_name'] = __name__
    return _get_package_discovery_extensions(*args, **kwargs)
