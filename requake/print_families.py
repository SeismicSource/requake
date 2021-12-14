#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Print families to screen.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
from .families import read_selected_families
from .rq_setup import rq_exit


def print_families(config):
    try:
        families = read_selected_families(config)
    except Exception as msg:
        logger.error(msg)
        rq_exit(1)

    header = '#n nev     lon      lat   depth '
    header += '                 start_time                    end_time'
    print(header)
    for family in families:
        print(family)
