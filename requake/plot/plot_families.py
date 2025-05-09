# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Download and plot traces for one or more event families.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import contextlib
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
from obspy.signal.filter import envelope
from obspy.signal.util import smooth
from ..config import config, rq_exit
from ..families import (
    FamilyNotFoundError,
    read_selected_families,
    get_family_aligned_waveforms_and_template
)
from ..waveforms import process_waveforms, NoWaveformError
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42
# unbind some keys, that we use it for interacting with the plot
mpl.rcParams['keymap.back'].remove('left')
mpl.rcParams['keymap.forward'].remove('right')
# the follwing keymap is not defined in mpl 3.5
with contextlib.suppress(KeyError):
    mpl.rcParams['keymap.all_axes'].remove('a')


def _plot_family(family):
    try:
        st = get_family_aligned_waveforms_and_template(family)
    except NoWaveformError as msg:
        logger.error(msg)
        return
    st = process_waveforms(st)

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
        p_arrival = tr0.stats.P_arrival_time - tr0.stats.starttime
        t0_p = p_arrival - 1
        t0_env = times[env > 0.1*env_max][0]
        t0 = min(t0_p, t0_env)
    if t1 is None:
        t1 = times[env > 0.3*env_max][-1]

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    tracelines = []
    p_bars = []
    s_bars = []
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
        color = '#cc8800' if average_trace else 'black'
        l, = ax.plot(tr.times()-t0, tr.data+n, color=color, linewidth=0.5)
        tracelines.append(l)
        p_arrival = tr.stats.P_arrival_time - tr.stats.starttime - t0
        s_arrival = tr.stats.S_arrival_time - tr.stats.starttime - t0
        hh = 0.15  # pick line half-height
        p_bar, = ax.plot((p_arrival, p_arrival), (n-hh, n+hh), color='g')
        s_bar, = ax.plot((s_arrival, s_arrival), (n-hh, n+hh), color='r')
        p_bars.append(p_bar)
        s_bars.append(s_bar)
        trans = ax.get_yaxis_transform()
        if average_trace:
            y_label = 'average'
            info_text = (
                f'{tr.stats.ev_lon:.4f}°E {tr.stats.ev_lat:.4f}°N '
                f'{tr.stats.ev_depth:.3f} km'
            )
        else:
            y_label = tr.stats.orig_time.strftime('%Y-%m-%d\n%H:%M:%S')
            mag_str = (
                f'{tr.stats.mag_type} {tr.stats.mag:.1f}'
                if tr.stats.mag else ''
            )
            info_text = (
                f'{tr.stats.evid} {mag_str}\n'
                f'{tr.stats.ev_lon:.4f}°E {tr.stats.ev_lat:.4f}°N '
                f'{tr.stats.ev_depth:.3f} km'
            )
        ax.text(
            -0.01, n, y_label, transform=trans, ha='right', va='center',
            color=color, fontsize=8, linespacing=1.5)
        txt = ax.text(
            0.01, n+0.2, info_text, transform=trans,
            color=color, fontsize=8, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        if not average_trace:
            text = f'CC mean {tr.stats.cc_mean:.2f}'
            txt = ax.text(
                0.98, n+0.2, text, ha='right',
                color=color, transform=trans, fontsize=8)
            txt.set_path_effects(
                [PathEffects.withStroke(linewidth=3, foreground='w')])
    legend = ax.legend(
        [p_bar, s_bar], ['P theo', 'S theo'], loc='lower right')
    legend.set_visible(False)
    for ps_bar in p_bars + s_bars:
        ps_bar.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(0, t1-t0)
    ax.set_xlabel('Time (s)')
    title = f'Family {family.number} | {len(st)-1} events'
    ax.set_title(title, loc='left')
    fig.canvas.manager.set_window_title(title)
    title = (
        f'{tr0.id} | {tr0.stats.distance:.1f} km | '
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f} Hz'
    )
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
        for ps_bar in p_bars + s_bars:
            ps_bar.set_visible(_toggle_arrivals.visible)
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


def plot_families():
    """"
    Plot traces for one or more event families.
    """
    try:
        families = read_selected_families()
    except (FileNotFoundError, FamilyNotFoundError) as msg:
        logger.error(msg)
        rq_exit(1)
    if len(families) > 20:
        logger.warning(
            f'Too many families selected: {len(families)}. '
            'Plotting only the first 20.')
        logger.info(
            'See "requake plot_families -h" for information on '
            'how to select specific families.')
        families = families[:20]
    for family in families:
        _plot_family(family)
    print('''
    Use left/right arrow keys to scroll backwards/forward in time.
    Use shift+left/shift+right to increase/decrease the time window.
    Use up/down arrow keys to increase/decrease trace amplitude.
    Press '0' to reset the view.
    Press 'a' to show/hide theoretical arrivals.
    Press 'q' to close a plot.
    ''')
    plt.show()
