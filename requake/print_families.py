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
import numpy as np
import sys
import csv
from tabulate import tabulate
from .families import read_selected_families
from .rq_setup import rq_exit
from .slip import mag_to_slip_in_cm


def print_families(config):
    try:
        families = read_selected_families(config)
    except Exception as msg:
        logger.error(msg)
        rq_exit(1)

    format_dict = {
        'simple': 'simple',
        'markdown': 'github'
    }
    headers = [
        'family',
        'nevents',
        'longitude',
        'latitude',
        'depth (km)',
        'start time',
        'end time',
        'duration (y)',
        'slip rate (cm/y)'
    ]
    floatfmt = [
        None,
        None,
        '.4f',
        '.4f',
        '.3f',
        None,
        None,
        '.2f',
        '.1f'
    ]
    table = list()
    format = config.args.format
    if format == 'csv':
        writer = csv.writer(sys.stdout)
        writer.writerow(headers)
    for family in families:
        row = [
            family.number,
            len(family),
            family.lon,
            family.lat,
            family.depth,
            family.starttime,
            family.endtime,
            family.duration
        ]
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        cum_slip = np.cumsum(slip)
        d_slip = cum_slip[-1] - cum_slip[0]
        slip_rate = d_slip/family.duration
        row.append(slip_rate)
        table.append(row)
    if format == 'csv':
        writer.writerows(table)
    else:
        format = format_dict[config.args.format]
        tab = tabulate(
            table, headers=headers, floatfmt=floatfmt, tablefmt=format)
        print(tab)
