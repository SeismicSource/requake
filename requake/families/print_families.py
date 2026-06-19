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
from obspy.geodetics import gps2dist_azimuth
from ..config import config, rq_exit
from ..config.generic_printer import _display_table
from .families import FamilyNotFoundError, read_selected_families
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _family_distance_stats(family):
    """
    Compute horizontal/vertical distance statistics for one family.

    Distances are computed from each event to the family centroid
    (mean lon/lat/depth).

    :param family: Family to process.
    :type family: requake.families.Family
    :return: hdist_min, hdist_max, vdist_min, vdist_max (all in km)
    :rtype: tuple
    """
    hdist = []
    if family.lon is not None and family.lat is not None:
        hdist.extend(
            gps2dist_azimuth(family.lat, family.lon, event.lat, event.lon)[0]
            / 1e3
            for event in family
            if event.lon is not None and event.lat is not None
        )
    vdist = []
    if family.depth is not None:
        vdist.extend(
            abs(event.depth - family.depth)
            for event in family
            if event.depth is not None
        )
    hdist_min = float(min(hdist)) if hdist else np.nan
    hdist_max = float(max(hdist)) if hdist else np.nan
    vdist_min = float(min(vdist)) if vdist else np.nan
    vdist_max = float(max(vdist)) if vdist else np.nan
    return hdist_min, hdist_max, vdist_min, vdist_max


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
    hdist_min, hdist_max, vdist_min, vdist_max = _family_distance_stats(family)
    if np.isnan(hdist_min) or np.isnan(hdist_max):
        print('Horizontal distance range: n/a')
    else:
        print(
            'Horizontal distance range: '
            f'{hdist_min:.3f} - {hdist_max:.3f} km'
        )
    if np.isnan(vdist_min) or np.isnan(vdist_max):
        print('Vertical distance range: n/a')
    else:
        print(f'Vertical distance range: {vdist_min:.3f} - {vdist_max:.3f} km')
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
        ('hdist\nmin (km)', '.3f'),
        ('hdist\nmax (km)', '.3f'),
        ('vdist\nmin (km)', '.3f'),
        ('vdist\nmax (km)', '.3f'),
        ('slip rate\n(cm/y)', '.1f'),
        ('mag\nmin', '.1f'),
        ('mag\nmax', '.1f')
    ]
    rows = []
    for family in families:
        hdist_min, hdist_max, vdist_min, vdist_max = _family_distance_stats(
            family
        )
        row = [
            family.number,
            len(family),
            family.lon,
            family.lat,
            family.depth,
            family.starttime,
            family.endtime,
            family.duration * duration_multiplier,
            hdist_min,
            hdist_max,
            vdist_min,
            vdist_max,
            family.slip_rate,
            family.magmin,
            family.magmax
        ]
        rows.append(row)
    _display_table(
        headers_fmt, rows,
        row_label='Families',
        copy_label='family',
        detail_title='Family Details',
    )


def _print_family_stats(families):
    """Print summary statistics for selected families."""
    nevents = np.array([len(family) for family in families], dtype=float)
    duration_days = np.array(
        [family.duration * 365 for family in families], dtype=float
    )
    mags_min = np.array([family.magmin for family in families], dtype=float)
    mags_max = np.array([family.magmax for family in families], dtype=float)
    hdist_max = np.array(
        [_family_distance_stats(family)[1] for family in families],
        dtype=float,
    )
    vdist_max = np.array(
        [_family_distance_stats(family)[3] for family in families],
        dtype=float,
    )

    print('Family statistics:')
    print(f'  Number of families: {len(families)}')
    print(f'  Total number of events: {int(np.sum(nevents))}')
    print(
        '  Events per family (min / median / mean / max): '
        f'{int(np.min(nevents))} / '
        f'{np.median(nevents):.1f} / '
        f'{np.mean(nevents):.1f} / '
        f'{int(np.max(nevents))}'
    )
    print(
        '  Family duration in days '
        '(min / median / mean / max): '
        f'{np.min(duration_days):.2f} / '
        f'{np.median(duration_days):.2f} / '
        f'{np.mean(duration_days):.2f} / '
        f'{np.max(duration_days):.2f}'
    )
    print(
        '  Family minimum magnitude '
        '(min / median / mean / max): '
        f'{np.nanmin(mags_min):.2f} / '
        f'{np.nanmedian(mags_min):.2f} / '
        f'{np.nanmean(mags_min):.2f} / '
        f'{np.nanmax(mags_min):.2f}'
    )
    print(
        '  Family maximum magnitude '
        '(min / median / mean / max): '
        f'{np.nanmin(mags_max):.2f} / '
        f'{np.nanmedian(mags_max):.2f} / '
        f'{np.nanmean(mags_max):.2f} / '
        f'{np.nanmax(mags_max):.2f}'
    )
    print(
        '  Horizontal distance max across families '
        '(min / median / mean / max) [km]: '
        f'{np.nanmin(hdist_max):.3f} / '
        f'{np.nanmedian(hdist_max):.3f} / '
        f'{np.nanmean(hdist_max):.3f} / '
        f'{np.nanmax(hdist_max):.3f}'
    )
    print(
        '  Vertical distance max across families '
        '(min / median / mean / max) [km]: '
        f'{np.nanmin(vdist_max):.3f} / '
        f'{np.nanmedian(vdist_max):.3f} / '
        f'{np.nanmean(vdist_max):.3f} / '
        f'{np.nanmax(vdist_max):.3f}'
    )


def print_families():
    """Print families to screen."""
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
    elif 1 / 24 < avg_duration_in_days < 1:
        duration_multiplier = 365 * 24
        duration_units = 'hours'
    else:
        duration_multiplier = 365 * 24 * 60
        duration_units = 'mins'

    if config.args.format == 'stats':
        _print_family_stats(families)
    elif config.args.detailed:
        for family in families:
            _print_family_details(family, duration_units, duration_multiplier)
            print()
    else:
        _print_family_list(families, duration_units, duration_multiplier)
