# Copyright 2022 Scott K Logan
# Licensed under the Apache License, Version 2.0

from pathlib import Path
import shutil
import sys

from colcon_core.plugin_system import satisfies_version
from colcon_core.task import run
from colcon_core.task import TaskExtensionPoint
from colcon_ros_buildfarm.package_import import get_package_import_extension


class BuildfarmReleaseBinaryBuildTask(TaskExtensionPoint):
    """Build ROS buildfarm release binary package jobs."""

    def __init__(self):  # noqa: D107
        super().__init__()
        satisfies_version(TaskExtensionPoint.EXTENSION_POINT_VERSION, '^1.0')

    async def release(self):  # noqa: D102
        args = self.context.args
        pkg = self.context.pkg
        ros_distro = str(pkg.path.parts[0])
        subdir = '.'.join((
            args.build_name, args.os_name, args.os_code_name, args.arch))
        staging_dir = Path(args.build_base) / subdir
        if staging_dir.exists():
            shutil.rmtree(str(staging_dir))
        staging_dir.mkdir(parents=True, exist_ok=True)

        self.progress('setup')
        script_path = staging_dir / 'job.sh'
        generation_cmd = [
            sys.executable, '-m',
            'ros_buildfarm.scripts.release.generate_release_script',
            args.config_url, ros_distro, args.build_name, pkg.name,
            args.os_name, args.os_code_name, args.arch, '--skip-source',
        ]
        gen_res = await run(self.context, generation_cmd, capture_output=True)
        gen_res.check_returncode()
        with script_path.open('wb') as script_file:
            script_file.write(gen_res.stdout)

        self.progress('build')
        exec_cmd = [
            '/usr/bin/env', 'sh',
            str(script_path), '-y',
        ]
        exec_res = await run(self.context, exec_cmd, cwd=str(staging_dir))
        exec_res.check_returncode()

        extension = get_package_import_extension(args)
        if not extension:
            return
        self.progress('import')
        await extension.import_binary(
            args, args.os_name, args.os_code_name, args.arch,
            staging_dir / 'binary')
