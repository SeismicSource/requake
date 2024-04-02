# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot utils.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import matplotlib.dates as mdates


def format_time_axis(ax, which='both'):
    """
    Format the time axis of a Matplotlib plot.
    """
    if which == 'both':
        axes = [ax.xaxis, ax.yaxis]
    elif which == 'xaxis':
        axes = [ax.xaxis]
    elif which == 'yaxis':
        axes = [ax.yaxis]
    else:
        raise ValueError(f'Invalid value for "which": {which}')
    for axis in axes:
        dmin, dmax = axis.get_data_interval()
        timespan = dmax-dmin
        if timespan > 365:
            _major_locator = mdates.YearLocator()   # every year
            _major_fmt = mdates.DateFormatter('%Y')
            _minor_locator = mdates.MonthLocator()  # every month
        else:
            _major_locator = mdates.AutoDateLocator(minticks=3, maxticks=7)
            _major_fmt = mdates.ConciseDateFormatter(_major_locator)
            _minor_locator = mdates.DayLocator()  # every day
        axis.set_major_locator(_major_locator)
        axis.set_major_formatter(_major_fmt)
        axis.set_minor_locator(_minor_locator)
        axis.grid(True, which='major', linestyle='--', color='0.5')
        axis.grid(True, which='minor', linestyle=':', color='0.8')
