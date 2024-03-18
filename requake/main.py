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


def main():
    """Main function for Requake."""
    from .config.parse_arguments import parse_arguments
    args = parse_arguments()
    from .config.rq_setup import configure, rq_exit
    config = configure(args)
    if config.args.action == 'read_catalog':
        from .catalog import read_catalog
        read_catalog(config)
    if config.args.action == 'scan_catalog':
        from .scan import scan_catalog
        scan_catalog(config)
    if config.args.action == 'scan_templates':
        from .scan import scan_templates
        scan_templates(config)
    if config.args.action == 'plot_pair':
        from .plot import plot_pair
        plot_pair(config)
    if config.args.action == 'build_families':
        from .families import build_families
        build_families(config)
    if config.args.action == 'print_families':
        from .families import print_families
        print_families(config)
    if config.args.action == 'plot_families':
        from .plot import plot_families
        plot_families(config)
    if config.args.action == 'plot_timespans':
        from .plot import plot_timespans
        plot_timespans(config)
    if config.args.action == 'plot_slip':
        from .plot import plot_slip
        plot_slip(config)
    if config.args.action == 'map_families':
        from .plot import map_families
        map_families(config)
    if config.args.action == 'flag_family':
        from .families import flag_family
        flag_family(config)
    if config.args.action == 'build_templates':
        from .families import build_templates
        build_templates(config)
    rq_exit(0)
