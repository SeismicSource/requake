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
from .plot_utils import format_time_axis, hover_annotation
from ..families.families import FamilyNotFoundError, read_selected_families
from ..formulas.slip import mag_to_slip_in_cm
from ..config.rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


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
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')

    cmap = mpl.colormaps['tab10']
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    for family in families:
        fn = family.number
        label = (
            f'Family {fn}\n{family.lon:.1f}°E {family.lat:.1f}°N '
            f'{family.depth:.1f} km'
        )
        times = [ev.orig_time.matplotlib_date for ev in family]
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        cum_slip = np.cumsum(slip)
        ax.step(
            times, cum_slip, where='post',
            lw=1, marker='o', color=cmap(norm(fn % 10)),
            label=label
        )
    # time axis formatting must be done here, before setting limits below
    format_time_axis(ax, which='xaxis')
    # get limits, that we will re-apply later
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    # now extend lines to zero slip at beginning and to final slip at the end
    for family in families:
        fn = family.number
        times = [ev.orig_time.matplotlib_date for ev in family]
        times = [times[0], ] + times + [times[-1]*2, ]
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        slip = [0, ] + slip + [0, ]
        cum_slip = np.cumsum(slip)
        ax.step(
            times, cum_slip, where='post',
            lw=1, marker='o', color=cmap(norm(fn % 10))
        )
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    ax.set_xlabel('Time')
    ax.set_ylabel('Cumulative Slip (cm)')
    ax.hover_annotation_element = 'lines'
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(10), ax=ax)
    cbar.ax.set_zorder(-1)
    cbar.ax.set_ylabel('mod(family number, 10)')

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
