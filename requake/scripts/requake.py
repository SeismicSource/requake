#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Main script for Requake.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""


def main():
    from ..parse_arguments import parse_arguments
    args = parse_arguments()
    from ..rq_setup import configure, rq_exit
    config = configure(args)
    if config.args.action == 'scan_catalog':
        from ..scan_catalog import scan_catalog
        scan_catalog(config)
    if config.args.action == 'plot_pair':
        from ..plot_pair import plot_pair
        plot_pair(config)
    if config.args.action == 'build_families':
        from ..build_families import build_families
        build_families(config)
    if config.args.action == 'plot_families':
        from ..plot_families import plot_families
        plot_families(config)
    if config.args.action == 'plot_timespans':
        from ..plot_timespans import plot_timespans
        plot_timespans(config)
    if config.args.action == 'map_families':
        from ..map_families import map_families
        map_families(config)
    if config.args.action == 'flag_family':
        from ..flag_family import flag_family
        flag_family(config)
    if config.args.action == 'build_templates':
        from ..build_templates import build_templates
        build_templates(config)
    rq_exit(0)
