#!/usr/bin/env python
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Main script for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
# Note: modules are lazily imported to speed up the startup time.
# pylint: disable=relative-beyond-top-level,import-outside-toplevel


# Map the action ids set by the command line to the function that
# implements each command.  The ids do not follow the command paths
# (e.g. "plot map" is "map_families"), so that the log files and the
# configuration keep their historical names.
_ACTIONS = {
    'read_catalog': ('.catalog', 'read_catalog'),
    'print_catalog': ('.catalog', 'print_catalog'),
    'print_catalogs': ('.catalog', 'print_catalogs'),
    'delete_catalog': ('.catalog', 'delete_catalog'),
    'edit_catalog': ('.catalog', 'edit_catalog'),
    'scan_catalog': ('.scan', 'scan_catalog'),
    'scan_templates': ('.scan', 'scan_templates'),
    'print_scans': ('.scan', 'print_scans'),
    'delete_scan': ('.scan', 'delete_scan'),
    'edit_scan': ('.scan', 'edit_scan'),
    'print_pairs': ('.families', 'print_pairs'),
    'dedup_events': ('.families', 'dedup_events'),
    'build_families': ('.families', 'build_families'),
    'build_templates': ('.families', 'build_templates'),
    'print_families': ('.families', 'print_families'),
    'print_family_builds': ('.families', 'print_family_builds'),
    'delete_build': ('.families', 'delete_family_build'),
    'edit_build': ('.families', 'edit_family_build'),
    'flag_family': ('.families', 'flag_family'),
    'plot_pair': ('.plot', 'plot_pair'),
    'plot_families': ('.plot', 'plot_families'),
    'plot_timespans': ('.plot', 'plot_timespans'),
    'plot_cumulative': ('.plot', 'plot_cumulative'),
    'map_families': ('.plot', 'map_families'),
    'wfcache_prefetch': ('.wfcache', 'wfcache_prefetch'),
    'wfcache_print': ('.wfcache', 'wfcache_print'),
    'wfcache_inspect': ('.wfcache', 'wfcache_inspect'),
    'wfcache_extract': ('.wfcache', 'wfcache_extract'),
    'wfcache_reset_failures': ('.wfcache', 'wfcache_reset_failures'),
}


def dispatch(action):
    """
    Run the function implementing a command.

    The module holding the function is imported here, and not at the top
    of this file, to keep the startup time short.

    :param action: the action id set by the command line
    :type action: str
    """
    from importlib import import_module
    target = _ACTIONS.get(action)
    if target is None:
        return
    package, function = target
    module = import_module(package, package=__package__)
    getattr(module, function)()


def run():
    """Run Requake."""
    from .cli import parse_arguments
    args = parse_arguments()
    from .config.rq_setup import configure, rq_exit
    configure(args)
    dispatch(args.action)
    rq_exit(0)


def main():
    """Run the main entry point for Requake."""
    try:
        run()
    # pylint: disable=broad-except
    except Exception as err:
        # pylint: disable=import-outside-toplevel
        from .database.db import is_abort_interruption
        if is_abort_interruption(err):
            # An aborted query is not a bug: exit like any other abort.
            from .config.rq_setup import rq_exit
            rq_exit(1, abort=True)
        from .config.utils import manage_uncaught_exception
        manage_uncaught_exception(err)
