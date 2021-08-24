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
from ..catalog_scan import scan_catalog


def main():
    config = configure()
    if config.catalog_based_scan:
        scan_catalog(config)
    rq_exit(0)
