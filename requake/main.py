#!/usr/bin/env python
# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Main script for Requake.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
# Note: modules are lazily imported to speed up the startup time.
# pylint: disable=relative-beyond-top-level,import-outside-toplevel


def run():
    """Run Requake."""
    from .config.parse_arguments import parse_arguments
    args = parse_arguments()
    from .config.rq_setup import configure, rq_exit
    configure(args)
    if args.action == 'read_catalog':
        from .catalog import read_catalog
        read_catalog()
    if args.action == 'print_catalog':
        from .catalog import print_catalog
        print_catalog()
    if args.action == 'scan_catalog':
        from .scan import scan_catalog
        scan_catalog()
    if args.action == 'print_pairs':
        from .families import print_pairs
        print_pairs()
    if args.action == 'scan_templates':
        from .scan import scan_templates
        scan_templates()
    if args.action == 'plot_pair':
        from .plot import plot_pair
        plot_pair()
    if args.action == 'build_families':
        from .families import build_families
        build_families()
    if args.action == 'print_families':
        from .families import print_families
        print_families()
    if args.action == 'plot_families':
        from .plot import plot_families
        plot_families()
    if args.action == 'plot_timespans':
        from .plot import plot_timespans
        plot_timespans()
    if args.action == 'plot_cumulative':
        from .plot import plot_cumulative
        plot_cumulative()
    if args.action == 'map_families':
        from .plot import map_families
        map_families()
    if args.action == 'flag_family':
        from .families import flag_family
        flag_family()
    if args.action == 'build_templates':
        from .families import build_templates
        build_templates()
    rq_exit(0)


def main():
    """Main entry point for Requake."""
    try:
        run()
    # pylint: disable=broad-except
    except Exception as err:
        from .config.utils import manage_uncaught_exception
        manage_uncaught_exception(err)
