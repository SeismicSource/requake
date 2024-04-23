# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Plot cumulative slip for one or more families.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib import colors
import numpy as np
from .plot_utils import (
    format_time_axis, plot_title, hover_annotation, duration_string)
from ..families.families import FamilyNotFoundError, read_selected_families
from ..formulas.slip import mag_to_slip_in_cm
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def _get_arrays(config, families):
    """
    Get arrays of times, cumulative slips, and labels for families.
    """
    times = [
        [ev.orig_time.matplotlib_date for ev in family]
        for family in families
    ]
    cumslips = [
        np.cumsum([mag_to_slip_in_cm(config, ev.mag) for ev in family])
        for family in families
    ]
    labels = [
        (
            f'Family {family.number}\n{family.lon:.1f}°E {family.lat:.1f}°N '
            f'{family.depth:.1f} km'
            f'\n{len(family)} evts {duration_string(family)}'
        )
        for family in families
    ]
    return times, cumslips, labels


def _format_axes(ax, times, cumslips):
    """
    Format axes for slip plot.
    """
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')
    format_time_axis(ax, which='xaxis')
    min_time = min(min(times) for times in times)
    max_time = max(max(times) for times in times)
    timespan = max_time - min_time
    padding = timespan * 0.05
    ax.set_xlim(min_time-padding, max_time+padding)
    min_cumslip = min(min(slip) for slip in cumslips)
    max_cumslip = max(max(slip) for slip in cumslips)
    cumslipspan = max_cumslip - min_cumslip
    padding = cumslipspan * 0.05
    ax.set_ylim(min_cumslip-padding, max_cumslip+padding)
    ax.set_xlabel('Time')
    ax.set_ylabel('Cumulative Slip (cm)')


def plot_slip(config):
    """
    Plot cumulative slip for one or more families.
    """
    try:
        families = read_selected_families(config)
    except (FileNotFoundError, FamilyNotFoundError) as m:
        logger.error(m)
        rq_exit(1)
    fig, ax = plt.subplots(figsize=(8, 4))

    cmap = mpl.colormaps['tab10']
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    times, cumslips, labels = _get_arrays(config, families)
    for family, time, cumslip, label in zip(families, times, cumslips, labels):
        # add an extra point at the beginning and at the end to make the step
        time = [time[0], ] + time + [time[-1]*2, ]
        cumslip = [0, ] + list(cumslip) + [cumslip[-1], ]
        ax.step(
            time, cumslip, where='post',
            lw=1, marker='o', color=cmap(norm(family.number % 10)),
            label=label
        )

    _format_axes(ax, times, cumslips)
    trace_ids = {family.trace_id for family in families if family.trace_id}
    plot_title(
        ax, len(families), trace_ids, vertical_position=1.05, fontsize=10)
    ax.hover_annotation_element = 'lines'
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(10), ax=ax)
    cbar.ax.set_zorder(-1)
    cbar.ax.set_ylabel('family number (last digit)')

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
