# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Print families to screen.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import numpy as np
from ..config import config, generic_printer, rq_exit
from .families import FamilyNotFoundError, read_selected_families
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _print_family_details(family, duration_units, duration_multiplier):
    """
    Print details of a family to screen.

    :param family: Family to print.
    :type family: requake.families.Family
    :param duration_units: Units for duration.
    :type duration_units: str
    :param duration_multiplier: Multiplier for duration.
    :type duration_multiplier: float
    """
    print(f'Family: {family.number}')
    print(f'Number of events: {len(family)}')
    print(f'Longitude: {family.lon:.4f}')
    print(f'Latitude: {family.lat:.4f}')
    print(f'Depth: {family.depth:.3f} km')
    print(f'Start time: {family.starttime}')
    print(f'End time: {family.endtime}')
    duration = family.duration * duration_multiplier
    print(f'Duration: {duration:.2f} {duration_units}')
    print(f'Slip rate: {family.slip_rate:.1f} cm/y')
    print(f'Magnitude range: {family.magmin:.1f} - {family.magmax:.1f}')
    print('Events:')
    for event in family:
        print(f'  {event}')


def _print_family_list(families, duration_units, duration_multiplier):
    """
    Print a list of families to screen.

    :param families: Families to print.
    :type families: list of requake.families.Family
    :param duration_units: Units for duration.
    :type duration_units: str
    :param duration_multiplier: Multiplier for duration.
    :type duration_multiplier: float
    """
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

    if config.args.detailed:
        for family in families:
            _print_family_details(family, duration_units, duration_multiplier)
            print()
    else:
        _print_family_list(families, duration_units, duration_multiplier)
