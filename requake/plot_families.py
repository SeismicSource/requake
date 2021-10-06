#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Download and plot traces for one or more event families.

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
import matplotlib as mpl
# unbind some keys, that we use it for interacting with the plot
mpl.rcParams['keymap.back'].remove('left')
mpl.rcParams['keymap.forward'].remove('right')
mpl.rcParams['keymap.all_axes'].remove('a')
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
from obspy.signal.filter import envelope
from obspy.signal.util import smooth
from .families import (
    build_family_number_list, read_families, get_family,
    get_family_aligned_waveforms_and_template)
from .waveforms import process_waveforms
from .rq_setup import rq_exit


def _plot_family(config, family):
    try:
        st = get_family_aligned_waveforms_and_template(config, family)
        st = process_waveforms(config, st)
    except Exception as m:
        logger.error(str(m))
        return

    t0 = config.args.starttime
    t1 = config.args.endtime
    # Use P_arrival and smooth envelope amplitude of first trace
    # to determine default time limits (if above values are None)
    tr0 = st[0]
    env = smooth(envelope(tr0.data), 200)
    env_max = env.max()
    times = tr0.times()
    if t0 is None:
        # For t0, take the earliest time between 10% of envelope
        # and theoretical P arrival
        P_arrival = tr0.stats.P_arrival_time - tr0.stats.starttime
        t0_P = P_arrival - 1
        t0_env = times[env > 0.1*env_max][0]
        t0 = min(t0_P, t0_env)
    if t1 is None:
        t1 = times[env > 0.3*env_max][-1]

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    tracelines = list()
    P_bars = list()
    S_bars = list()
    for n, tr in enumerate(st.sort()):
        average_trace = 'average' in tr.stats.evid
        # Normalize trace between t0 and t1
        tt0 = tr.stats.starttime + t0
        tt1 = tr.stats.starttime + t1
        tr2 = tr.copy().trim(tt0, tt1)
        tr.data /= abs(tr2.max())
        tr.detrend('demean')
        tr.data *= 0.5
        # substract t0, so that time axis starts at 0
        if average_trace:
            color = '#cc8800'
        else:
            color = 'black'
        l, = ax.plot(tr.times()-t0, tr.data+n, color=color, linewidth=0.5)
        tracelines.append(l)
        P_arrival = tr.stats.P_arrival_time - tr.stats.starttime - t0
        S_arrival = tr.stats.S_arrival_time - tr.stats.starttime - t0
        hh = 0.15  # pick line half-height
        P_bar, = ax.plot((P_arrival, P_arrival), (n-hh, n+hh), color='g')
        S_bar, = ax.plot((S_arrival, S_arrival), (n-hh, n+hh), color='r')
        P_bars.append(P_bar)
        S_bars.append(S_bar)
        trans = ax.get_yaxis_transform()
        if average_trace:
            y_label = 'average'
            info_text = '{:.4f}°E {:.4f}°N {:.3f} km'.format(
                tr.stats.ev_lon, tr.stats.ev_lat, tr.stats.ev_depth)
        else:
            y_label = tr.stats.orig_time.strftime('%Y-%m-%d\n%H:%M:%S')
            info_text = '{} {} {:.1f}\n'.format(
                tr.stats.evid, tr.stats.mag_type, tr.stats.mag)
            info_text += '{:.4f}°E {:.4f}°N {:.3f} km'.format(
                tr.stats.ev_lon, tr.stats.ev_lat, tr.stats.ev_depth)
        ax.text(
            -0.01, n, y_label, transform=trans, ha='right', va='center',
            color=color, fontsize=8, linespacing=1.5)
        txt = ax.text(
            0.01, n+0.2, info_text, transform=trans,
            color=color, fontsize=8, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        if not average_trace:
            text = 'CC mean {:.2f}'.format(tr.stats.cc_mean)
            txt = ax.text(
                0.98, n+0.2, text, ha='right',
                color=color, transform=trans, fontsize=8)
            txt.set_path_effects(
                [PathEffects.withStroke(linewidth=3, foreground='w')])
    legend = ax.legend(
        [P_bar, S_bar], ['P theo', 'S theo'], loc='lower right')
    legend.set_visible(False)
    for bar in P_bars + S_bars:
        bar.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(0, t1-t0)
    ax.set_xlabel('Time (s)')
    title = 'Family {} | {} events'.format(family.number, len(st)-1)
    ax.set_title(title, loc='left')
    fig.canvas.manager.set_window_title(title)
    title = '{} | {:.1f} km | {:.1f}-{:.1f} Hz'.format(
        tr0.id, tr0.stats.distance, config.cc_freq_min, config.cc_freq_max)
    ax.set_title(title, loc='right')

    def _zoom_lines(zoom_level):
        for line in tracelines:
            ydata = line.get_ydata()
            ymean = ydata.mean()
            ydata = (ydata-ymean)*zoom_level + ymean
            line.set_ydata(ydata)
        fig.canvas.draw_idle()

    def _time_zoom(ax, zoom_level):
        xmin, xmax = ax.get_xlim()
        xmean = 0.5*(xmin+xmax)
        xspan = xmax-xmin
        xspan *= zoom_level
        xmin = xmean - 0.5*xspan
        xmax = xmean + 0.5*xspan
        ax.set_xlim(xmin, xmax)
        fig.canvas.draw_idle()

    def _pan_plot(ax, amount):
        xlim = ax.get_xlim()
        ax.set_xlim(xlim[0]+amount, xlim[1]+amount)
        fig.canvas.draw_idle()

    def _toggle_arrivals():
        _toggle_arrivals.visible = not _toggle_arrivals.visible
        for bar in P_bars + S_bars:
            bar.set_visible(_toggle_arrivals.visible)
        legend.set_visible(_toggle_arrivals.visible)
        fig.canvas.draw_idle()
    _toggle_arrivals.visible = False

    def _keypress(event):
        ax = event.canvas.figure.axes[0]
        if event.key == 'up':
            _keypress.zoom_level *= 2
            _zoom_lines(2)
        if event.key == 'down':
            _keypress.zoom_level /= 2
            _zoom_lines(0.5)
        elif event.key == 'right':
            _keypress.pan_amount += 1
            _pan_plot(ax, 1)
        elif event.key == 'left':
            _keypress.pan_amount -= 1
            _pan_plot(ax, -1)
        elif event.key == 'shift+right':
            _keypress.time_zoom_level /= 2
            _time_zoom(ax, 0.5)
        elif event.key == 'shift+left':
            _keypress.time_zoom_level *= 2
            _time_zoom(ax, 2)
        elif event.key == '0':
            _zoom_lines(1./_keypress.zoom_level)
            _time_zoom(ax, 1./_keypress.time_zoom_level)
            _pan_plot(ax, -_keypress.pan_amount)
            _keypress.zoom_level = 1
            _keypress.time_zoom_level = 1
            _keypress.pan_amount = 0
        elif event.key == 'a':
            _toggle_arrivals()
    _keypress.zoom_level = 1
    _keypress.time_zoom_level = 1
    _keypress.pan_amount = 0
    fig.canvas.mpl_connect('key_press_event', _keypress)


def plot_families(config):
    try:
        family_numbers = build_family_number_list(config)
        families = read_families(config)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)
    for family_number in family_numbers:
        try:
            family = get_family(config, families, family_number)
            _plot_family(config, family)
        except Exception as m:
            logger.error(str(m))
            continue
    print('''
    Use left/right arrow keys to scroll backwards/forward in time.
    Use shift+left/shift+right to increase/decrease the time window.
    Use up/down arrow keys to increase/decrease trace amplitude.
    Press '0' to reset the view.
    Press 'a' to show/hide theoretical arrivals.
    Press 'q' to close a plot.
    ''')
    plt.show()
