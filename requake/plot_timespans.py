#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Plot family timespans.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.cm as cm
import matplotlib.colors as colors
import numpy as np
from .families import read_families
from .rq_setup import rq_exit


def plot_timespans(config):
    families = read_families(config)
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

    cmap = cm.tab10
    norm = colors.Normalize(vmin=-0.5, vmax=9.5)
    lines = list()
    if config.args.sortby is not None:
        sort_by = config.args.sortby
        valid_sort_by = (
            'time', 'latitude', 'longitude', 'depth', 'distance_from')
        if sort_by not in valid_sort_by:
            msg = 'Invalid value for "sortby". Choose from: {}.'.format(
                valid_sort_by
            )
            logger.error(msg)
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
        ax.yaxis.set_major_locator(years)
        ax.yaxis.set_major_formatter(yearsFmt)
        ax.yaxis.set_minor_locator(months)
    for family in families:
        fn = family.number
        if not family.valid:
            msg = 'Family "{}" is flagged as not valid'.format(fn)
            logger.warning(msg)
            continue
        if (family.endtime - family.starttime) < config.args.longerthan:
            msg = 'Family "{}" is too short'.format(fn)
            logger.warning(msg)
            continue
        label = 'Family {}\n{:.1f}°E {:.1f}°N {:.1f} km'.format(
            fn, family.lon, family.lat, family.depth)
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
            ylabel = 'Distance from {:.1f}°E, {:.1f}°N (km)'.format(lon0, lat0)
        line, = ax.plot(
            times, yvals, lw=1, marker='o', color=cmap(norm(fn % 10)),
            label=label)
        lines.append(line)
    ax.set_xlabel('Time')
    ax.set_ylabel(ylabel)
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
