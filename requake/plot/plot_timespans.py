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
import numpy as np
from ..config import config, rq_exit
from ..families import FamilyNotFoundError, read_selected_families
from .plot_utils import (
    format_time_axis, plot_title, hover_annotation, duration_string,
    family_colors, plot_colorbar
)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


ylabels = {
    'depth': 'Depth (km)',
    'distance_from': 'Distance from',
    'family_number': 'Family Number',
    'latitude': 'Latitude (°N)',
    'longitude': 'Longitude (°E)',
    'time': 'Family Start Time',
}


def _plot_family_timespans(family, ax, sort_by, lon0, lat0, color):
    """
    Plot the timespan of a single family.
    """
    fn = family.number
    nevents = len(family)
    duration_str = duration_string(family)
    label = (
        f'Family {fn}\n{family.lon:.1f}°E {family.lat:.1f}°N '
        f'{family.depth:.1f} km'
        f'\n{nevents} evts {duration_str}'
    )
    times = [ev.orig_time.matplotlib_date for ev in family]
    if sort_by == 'depth':
        yvals = np.ones(len(times)) * family.depth
    elif sort_by == 'distance_from':
        yvals = np.ones(len(times)) * family.distance_from(lon0, lat0)
    elif sort_by == 'family_number':
        yvals = np.ones(len(times)) * fn
    elif sort_by == 'latitude':
        yvals = np.ones(len(times)) * family.lat
    elif sort_by == 'longitude':
        yvals = np.ones(len(times)) * family.lon
    elif sort_by == 'time':
        yvals = np.ones(len(times)) * family.starttime.matplotlib_date
    brightness = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
    linecolor = (0, 0, 0) if brightness > 0.8 else color
    ax.plot(
        times, yvals, lw=1, marker='o',
        color=linecolor, mfc=color, mec=linecolor, label=label
    )


def plot_timespans():
    """
    Plot family timespans.
    """
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')

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
    try:
        fcolors, norm, cmap = family_colors(families)
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    trace_ids = []
    for family, color in zip(families, fcolors):
        if family.trace_id not in trace_ids and family.trace_id is not None:
            trace_ids.append(family.trace_id)
        _plot_family_timespans(family, ax, sort_by, lon0, lat0, color)
    ax.callbacks.connect('xlim_changed', format_time_axis)
    if sort_by == 'time':
        ax.callbacks.connect(
            'ylim_changed', lambda ax: format_time_axis(ax, which='yaxis'))
    ax.set_xlabel('Time')
    if sort_by == 'distance_from':
        ylabel = f'{ylabels[sort_by]} ({lat0:.1f}°N,{lon0:.1f}°E) (km)'
    else:
        ylabel = ylabels[sort_by]
    ax.set_ylabel(ylabel)
    plot_title(
        ax, len(families), trace_ids, vertical_position=1.05, fontsize=10)
    ax.hover_annotation_element = 'lines'
    plot_colorbar(fig, ax, cmap, norm)

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox={'boxstyle': 'round', 'fc': 'w'},
        zorder=20
    )
    annot.set_visible(False)
    annot.hover_annotation = True
    fig.canvas.mpl_connect('motion_notify_event', hover_annotation)
    plt.show()
