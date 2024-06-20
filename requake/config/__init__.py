# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Configuration and initialization of the Requake package.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .rq_setup import rq_exit  # noqa
from .generic_printer import generic_printer  # noqa
# The config object is created in config.py and needs to be populated
# when using requake from command line, this is done by the configure()
# function in rq_setup.py
from .config import config  # noqa
