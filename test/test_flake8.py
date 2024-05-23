# Copyright 2018 Open Source Robotics Foundation, Inc.
# Licensed under the Apache License, Version 2.0

import os
import subprocess
import sys

import pytest


@pytest.mark.flake8
@pytest.mark.linter
def test_flake8():
    # flake8 doesn't have a stable public API as of ver 6.1.0.
    # See: https://flake8.pycqa.org/en/latest/user/python-api.html
    # Calling through subprocess is the most stable way to run it.

    ret_code = subprocess.call(
        [sys.executable, '-m', 'flake8'],
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert 0 == ret_code, 'flake8 found violations'
