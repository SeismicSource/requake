# -*- coding: utf8 -*-
"""
Plot cumulative slip for one or more families.

:copyright:
    2021-2022 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cm as cm
import matplotlib.colors as colors
import numpy as np
from .families import read_selected_families
from .slip import mag_to_slip_in_cm
from .rq_setup import rq_exit

logger = logging.getLogger(__name__.split('.')[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def plot_slip(config):
    try:
        families = read_selected_families(config)
    except Exception as msg:
        logger.error(msg)
        rq_exit(1)
    fig, ax = plt.subplots(figsize=(8, 4))
    years = mdates.YearLocator()   # every year
    months = mdates.MonthLocator()  # every month
    yearsFmt = mdates.DateFormatter('%Y')
    ax.xaxis.set_major_locator(years)
    ax.xaxis.set_major_formatter(yearsFmt)
    ax.xaxis.set_minor_locator(months)
    ax.xaxis.grid(True)
    ax.tick_params(which='both', top=True, labeltop=True)
    ax.tick_params(axis='x', which='both', direction='in')

    cmap = cm.tab10
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    lines = list()
    for family in families:
        fn = family.number
        label = 'Family {}\n{:.1f}°E {:.1f}°N {:.1f} km'.format(
            fn, family.lon, family.lat, family.depth)
        times = [ev.orig_time.matplotlib_date for ev in family]
        slip = [mag_to_slip_in_cm(config, ev.mag) for ev in family]
        cum_slip = np.cumsum(slip)
        line, = ax.step(
            times, cum_slip, where='post',
            lw=1, marker='o', color=cmap(norm(fn % 10)),
            label=label)
        lines.append(line)
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
    sm = cm.ScalarMappable(cmap=cmap, norm=norm)
    cbar = fig.colorbar(sm, ticks=range(0, 10))
    cbar.ax.set_ylabel('mod(family number, 10)')

    # Empty annotation that will be updated interactively
    annot = ax.annotate(
        '', xy=(0, 0), xytext=(5, 5),
        textcoords='offset points',
        bbox=dict(boxstyle='round', fc='w'),
        zorder=20
    )
    annot.set_visible(False)

    def hover(event):
        vis = annot.get_visible()
        if event.inaxes == ax:
            for line in lines:
                cont, ind = line.contains(event)
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
                else:
                    line.set_linewidth(1)
                    if vis:
                        annot.set_visible(False)
                        fig.canvas.draw_idle()
    fig.canvas.mpl_connect('motion_notify_event', hover)

    plt.show()
