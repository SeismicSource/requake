# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot family timespans.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import cm
from matplotlib import colors
import numpy as np
from ..families.families import FamilyNotFoundError, read_selected_families
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def plot_timespans(config):
    """
    Plot family timespans.
    """
    try:
        families = read_selected_families(config)
    except (FileNotFoundError, FamilyNotFoundError) as m:
        logger.error(m)
        rq_exit(1)
    fig, ax = plt.subplots(figsize=(8, 8))
    years = mdates.YearLocator()   # every year
    months = mdates.MonthLocator()  # every month
    yearsFmt = mdates.DateFormatter('%Y')
    ax.xaxis.set_major_locator(years)
    ax.xaxis.set_major_formatter(yearsFmt)
    ax.xaxis.set_minor_locator(months)
    ax.xaxis.grid(True)
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')

    cmap = mpl.colormaps['tab10']
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    lines = []
    if config.args.sortby is not None:
        sort_by = config.args.sortby
        valid_sort_by = (
            'time', 'latitude', 'longitude', 'depth', 'distance_from',
            'family_number'
        )
        if sort_by not in valid_sort_by:
            logger.error(
                f'Invalid value for "sortby". Choose from: {valid_sort_by}.'
            )
            rq_exit(1)
    else:
        sort_by = config.sort_families_by
    lon0, lat0 = config.distance_from_lon, config.distance_from_lat
    if sort_by == 'distance_from' and (lon0 is None or lat0 is None):
        logger.error(
            '"sort_families_by" set to "distance_from", '
            'but "distance_from_lon" and/or "distance_from_lat" '
            'are not specified')
        rq_exit(1)
    if sort_by == 'time':
        years = mdates.YearLocator()   # every year
        months = mdates.MonthLocator()  # every month
        yearsFmt = mdates.DateFormatter('%Y')
        ax.yaxis.set_major_locator(years)
        ax.yaxis.set_major_formatter(yearsFmt)
        ax.yaxis.set_minor_locator(months)
    for family in families:
        fn = family.number
        label = (
            f'Family {fn}\n{family.lon:.1f}°E {family.lat:.1f}°N '
            f'{family.depth:.1f} km'
        )
        times = [ev.orig_time.matplotlib_date for ev in family]
        if sort_by == 'time':
            yvals = np.ones(len(times)) * family.starttime.matplotlib_date
            ylabel = 'Family Start Time'
        if sort_by == 'latitude':
            yvals = np.ones(len(times)) * family.lat
            ylabel = 'Latitude (°N)'
        elif sort_by == 'longitude':
            yvals = np.ones(len(times)) * family.lon
            ylabel = 'Longitude (°E)'
        elif sort_by == 'depth':
            yvals = np.ones(len(times)) * family.depth
            ylabel = 'Depth (km)'
        elif sort_by == 'distance_from':
            yvals = np.ones(len(times)) * family.distance_from(lon0, lat0)
            ylabel = f'Distance from {lon0:.1f}°E, {lat0:.1f}°N (km)'
        elif sort_by == 'family_number':
            yvals = np.ones(len(times)) * fn
            ylabel = 'Family Number'
        line, = ax.plot(
            times, yvals, lw=1, marker='o', color=cmap(norm(fn % 10)),
            label=label)
        lines.append(line)
    ax.set_xlabel('Time')
    ax.set_ylabel(ylabel)
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(10), ax=ax)
    cbar.ax.set_ylabel('mod(family number, 10)')

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox={'boxstyle': 'round', 'fc': 'w'},
        zorder=20
    )
    annot.set_visible(False)

    def hover(event):
        vis = annot.get_visible()
        if event.inaxes == ax:
            for line in lines:
                cont, _ind = line.contains(event)
                if cont:
                    color = line.get_color()
                    line.set_linewidth(3)
                    annot.xy = (event.xdata, event.ydata)
                    annot.set_text(line.get_label())
                    annot.get_bbox_patch().set_facecolor(color)
                    annot.get_bbox_patch().set_alpha(0.8)
                    annot.set_visible(True)
                    fig.canvas.draw_idle()
                    break
                line.set_linewidth(1)
                if vis:
                    annot.set_visible(False)
                    fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', hover)

    plt.show()
