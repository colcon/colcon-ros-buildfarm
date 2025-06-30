# Copyright 2024 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

from typing import Any

from colcon_core.command \
    import LOG_LEVEL_ENVIRONMENT_VARIABLE \
    as COLCON_LOG_LEVEL_ENVIRONMENT_VARIABLE
from colcon_core.command import main as colcon_main
from colcon_core.environment_variable import EnvironmentVariable

"""Environment variable to set the log level"""
LOG_LEVEL_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'ROS_BUILDFARM_LOG_LEVEL',
    COLCON_LOG_LEVEL_ENVIRONMENT_VARIABLE.description)

"""Environment variable to set the configuration directory"""
HOME_ENVIRONMENT_VARIABLE = EnvironmentVariable(
    'ROS_BUILDFARM_HOME',
    'Set the configuration directory (default: ~/.ros_buildfarm)')


def main(*args: str, **kwargs: str) -> Any:
    """Execute the main logic of the command."""
    colcon_kwargs = {
        'command_name': 'ros_buildfarm',
        'verb_group_name': 'colcon_ros_buildfarm.verb',
        'environment_variable_group_name':
            'colcon_ros_buildfarm.environment_variable',
        **kwargs,
    }
    return colcon_main(*args, **colcon_kwargs)
