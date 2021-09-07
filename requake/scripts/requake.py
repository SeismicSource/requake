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
from ..rq_setup import configure, rq_exit
from ..scan_catalog import scan_catalog
from ..plot_pair import plot_pair
from ..build_families import build_families
from ..plot_families import plot_families


def main():
    config = configure()
    if config.args.action == 'scan_catalog':
        scan_catalog(config)
    if config.args.action == 'plot_pair':
        plot_pair(config)
    if config.args.action == 'build_families':
        build_families(config)
    if config.args.action == 'plot_families':
        plot_families(config)
    rq_exit(0)
