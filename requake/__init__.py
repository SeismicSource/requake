# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Initialize requake package.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import multiprocessing
import signal

# Child processes spawned for parallel scans may import requake before worker
# initializers run. Ignore SIGINT early in children so Ctrl+C is managed by
# the parent process only.
if multiprocessing.current_process().name != 'MainProcess':
    signal.signal(signal.SIGINT, signal.SIG_IGN)

from . import _version
__version__ = _version.get_versions()['version']
