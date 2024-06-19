# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print families to screen.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import numpy as np
from .families import FamilyNotFoundError, read_selected_families
from ..config.generic_printer import generic_printer
from ..config import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def print_families():
    """
    Print families to screen.
    """
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)

    # determine duration units
    average_duration = np.mean([f.duration for f in families])
    avg_duration_in_days = average_duration * 365
    if 30 < avg_duration_in_days < 365:
        duration_multiplier = 12
        duration_units = 'mons'
    elif 1 < avg_duration_in_days < 30:
        duration_multiplier = 365
        duration_units = 'days'
    elif 1/24 < avg_duration_in_days < 1:
        duration_multiplier = 365 * 24
        duration_units = 'hours'
    else:
        duration_multiplier = 365 * 24 * 60
        duration_units = 'mins'

    headers_fmt = [
        ('family', None),
        ('nevents', None),
        ('longitude', '.4f'),
        ('latitude', '.4f'),
        ('depth\n(km)', '.3f'),
        ('start time', None),
        ('end time', None),
        (f'duration\n({duration_units})', '.2f'),
        ('slip rate\n(cm/y)', '.1f'),
        ('mag\nmin', '.1f'),
        ('mag\nmax', '.1f')
    ]
    rows = []
    for family in families:
        row = [
            family.number,
            len(family),
            family.lon,
            family.lat,
            family.depth,
            family.starttime,
            family.endtime,
            family.duration*duration_multiplier,
            family.slip_rate,
            family.magmin,
            family.magmax
        ]
        rows.append(row)
    generic_printer(rows, headers_fmt)
