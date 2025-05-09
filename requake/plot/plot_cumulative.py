# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Cumulative plot for one or more families.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
from ..config import config, rq_exit
from ..families import FamilyNotFoundError, read_selected_families
from ..formulas import mag_to_slip_in_cm, mag_to_moment
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


def _get_arrays(families):
    """
    Get arrays of times, cumulative quantities, and labels for families.
    """
    times = [
        [ev.orig_time.matplotlib_date for ev in family]
        for family in families
    ]
    if config.args.quantity == 'slip':
        cumuls = [
            np.cumsum([mag_to_slip_in_cm(ev.mag) for ev in family])
            for family in families
        ]
    elif config.args.quantity == 'moment':
        cumuls = [
            np.cumsum([mag_to_moment(ev.mag) for ev in family])
            for family in families
        ]
    elif config.args.quantity == 'number':
        cumuls = [
            np.arange(1, len(family)+1)
            for family in families
        ]
    else:
        raise ValueError(f'Unknown quantity: {config.args.quantity}')
    labels = [
        (
            f'Family {family.number}\n{family.lon:.1f}°E {family.lat:.1f}°N '
            f'{family.depth:.1f} km'
            f'\n{len(family)} evts {duration_string(family)}'
        )
        for family in families
    ]
    return times, cumuls, labels


def _format_axes(ax, times, cumuls):
    """
    Format axes for cumulative plot.
    """
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.callbacks.connect('xlim_changed', format_time_axis)
    min_time = min(min(times) for times in times)
    max_time = max(max(times) for times in times)
    timespan = max_time - min_time
    padding = timespan * 0.05
    ax.set_xlim(min_time-padding, max_time+padding)
    min_cumul = min(min(c) for c in cumuls)
    max_cumul = max(max(c) for c in cumuls)
    cumulspan = max_cumul - min_cumul
    if not config.args.logscale:
        padding = cumulspan * 0.05
        min_cumul = max(min_cumul - padding, 0)
        max_cumul += padding
    else:
        if min_cumul == 0:
            # use second smallest value to avoid log(0)
            min_cumul = sorted({min(c) for c in cumuls})[1]
        min_cumul /= 10
        max_cumul *= 10
    ax.set_ylim(min_cumul, max_cumul)
    ax.set_xlabel('Time')
    if config.args.quantity == 'slip':
        ax.set_ylabel('Cumulative Slip (cm)')
    elif config.args.quantity == 'moment':
        ax.set_ylabel('Cumulative Moment (N·m)')
        # move and resize the scientific notation exponent, so that it does
        # not overlap with the top y-axis label
        txt = ax.yaxis.get_offset_text()
        txt.set_x(-0.03)
        txt.set_fontsize(8)
        txt.set_horizontalalignment('right')
    elif config.args.quantity == 'number':
        ax.set_ylabel('Cumulative Number of Events')
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    else:
        raise ValueError(f'Unknown quantity: {config.args.quantity}')


def plot_cumulative():
    """
    Cumulative plot for one or more families.
    """
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    fig, ax = plt.subplots(figsize=(8, 4))
    if config.args.logscale:
        ax.set_yscale('log')

    try:
        fcolors, norm, cmap = family_colors(families)
        times, cumuls, labels = _get_arrays(families)
    except ValueError as msg:
        logger.error(msg)
        rq_exit(1)
    maxtime = max(max(time) for time in times)
    mintime = min(min(time) for time in times)
    maxtime += (maxtime - mintime) * 0.1
    mincumul = min(min(cumul) for cumul in cumuls)
    maxcumul = max(max(cumul) for cumul in cumuls)
    mincumul = max(mincumul - (maxcumul - mincumul) * 0.1, 0)
    for time, cumul, label, color in zip(times, cumuls, labels, fcolors):
        brightness = 0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2]
        linecolor = (0, 0, 0) if brightness > 0.8 else color
        # fist plot just the markers
        ax.scatter(
            time, cumul, marker='o',
            color=color, edgecolor=linecolor, label=label, zorder=20
        )
        # add an extra point at the beginning and at the end to make the step
        time = [time[0], ] + time + [maxtime, ]
        cumul = [mincumul, ] + list(cumul) + [cumul[-1], ]
        pe = []
        if linecolor != color:
            # add a patheffect to the line to give it a contrasting border
            pe.append(
                mpl.patheffects.withStroke(linewidth=2, foreground=linecolor)
            )
        ax.step(
            time, cumul, where='post', lw=1, marker='', color=color,
            path_effects=pe, label=label, zorder=10
        )

    trace_ids = {family.trace_id for family in families if family.trace_id}
    plot_title(
        ax, len(families), trace_ids, vertical_position=1.05, fontsize=10)
    ax.hover_annotation_element = 'lines'
    plot_colorbar(fig, ax, cmap, norm)
    # format axes after adding colorbar to avoid a visual glitch
    _format_axes(ax, times, cumuls)

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
