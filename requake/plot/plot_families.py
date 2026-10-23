# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Download and plot traces for one or more event families.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
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
from .plot_utils import save_or_show_plot
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

# Number of traces above which the trace amplitude is scaled up, so that
# waveforms remain visible even when traces overlap each other.
AMPLITUDE_REF_TRACES = 35
MAX_AMPLITUDE = 15
# Trace amplitude, in trace spacings, used in classic mode
BASE_AMPLITUDE = 0.5
# Line styles
DEFAULT_LINEWIDTH = 0.5
LABELED_LINEWIDTH = 1.0
UNLABELED_LINEWIDTH = 0.25
UNLABELED_COLOR = 'black'
# Alpha used for the unlabeled traces when there are
# UNLABELED_ALPHA_REF_TRACES unlabeled traces; with more unlabeled
# traces, they are drawn lighter, to compensate for overplotting
UNLABELED_ALPHA = 0.7
UNLABELED_ALPHA_REF_TRACES = 100
# Color of the average (template) trace
AVERAGE_COLOR = '#cc8800'
# Font size of the trace labels
LABEL_FONTSIZE = 8
# Default maximum number of labeled traces, when --max-labels is not given
DEFAULT_MAX_LABELS = 15


def _labeled_rows(ntraces, max_labels):
    """
    Return the rows of a family plot that carry a label.

    At most ``max_labels`` rows are labeled, evenly spaced across the
    plot. The first and the last rows are always labeled, so that the
    top and bottom traces of a wiggle plot always have a label.

    When the labels would end up on adjacent rows, all the rows are
    labeled instead.

    :param ntraces: Number of traces in the plot.
    :type ntraces: int
    :param max_labels: Maximum number of labeled traces; 0 or less means
        no limit.
    :type max_labels: int
    :return: row positions
    :rtype: list
    """
    if max_labels <= 0 or max_labels >= ntraces:
        return list(range(ntraces))
    if max_labels == 1:
        return [ntraces - 1]
    step = (ntraces - 1) / (max_labels - 1)
    if round(step) < 2:
        return list(range(ntraces))
    return [round(n * step) for n in range(max_labels)]


def _ordinal(number):
    """
    Return the ordinal string for a number, e.g. "1st", "2nd", "3rd".

    :param number: the number
    :type number: int
    :return: the ordinal string
    :rtype: str
    """
    if 10 <= number % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    return f'{number}{suffix}'


def _max_labels():
    """
    Return the maximum number of labeled traces.

    Use the ``--max-labels`` value, if given, or the default value.

    :return: maximum number of labeled traces
    :rtype: int
    """
    max_labels = getattr(config.args, 'max_labels', None)
    return DEFAULT_MAX_LABELS if max_labels is None else max_labels


def _warn_if_max_labels_ignored(family, nlabels):
    """
    Warn when the user-given ``--max-labels`` limit cannot be honored.

    There are too few traces to leave some of them unlabeled, so all the
    traces are labeled. No warning is issued when ``--max-labels`` is not
    given on the command line.

    :param family: family being plotted
    :type family: Family
    :param nlabels: number of traces actually labeled
    :type nlabels: int
    """
    max_labels = getattr(config.args, 'max_labels', None)
    if max_labels is None:
        return
    if 0 < max_labels < nlabels:
        logger.warning(
            f'Family {family.number}: not enough traces to apply '
            f'--max-labels ({max_labels}), labeling all the traces'
        )


def _trace_amplitude(ntraces, ref_traces=AMPLITUDE_REF_TRACES,
                     max_amplitude=MAX_AMPLITUDE):
    """
    Return the amplitude of the traces of a family plot.

    For families with many events, the amplitude is scaled up so that the
    waveform shape remains visible in the figure; traces will then overlap
    each other.

    :param ntraces: Number of traces in the plot.
    :type ntraces: int
    :param ref_traces: Number of traces for which the base amplitude is used.
    :type ref_traces: int
    :param max_amplitude: Maximum amplitude, in trace spacings.
    :type max_amplitude: float
    :return: Trace amplitude, in trace spacings.
    :rtype: float
    """
    amplitude = BASE_AMPLITUDE * max(1, ntraces / ref_traces)
    return min(amplitude, max_amplitude)


def _unlabeled_alpha(ntraces, nlabeled, base_alpha=UNLABELED_ALPHA,
                     ref_traces=UNLABELED_ALPHA_REF_TRACES):
    """
    Return the alpha of the unlabeled traces of a family plot.

    The more traces are left unlabeled, the lighter they are drawn, so
    that overlapping traces do not make the plot too dark.

    :param ntraces: Number of traces in the plot.
    :type ntraces: int
    :param nlabeled: Number of labeled traces.
    :type nlabeled: int
    :param base_alpha: Alpha used for ``ref_traces`` unlabeled traces.
    :type base_alpha: float
    :param ref_traces: Number of unlabeled traces for which the base alpha
        is used.
    :type ref_traces: int
    :return: Alpha value, between 0 and 1.
    :rtype: float
    """
    nunlabeled = ntraces - nlabeled
    if nunlabeled <= 0:
        return base_alpha
    return base_alpha * min(1, (ref_traces / nunlabeled) ** 0.75)


def _time_limits(st):
    """
    Return the time window used to plot the traces of a family.

    The window is taken from the command line options, if given. Otherwise,
    it is derived from the envelope of the first trace and from its
    theoretical P arrival.

    :param st: stream of aligned traces
    :type st: obspy.Stream
    :return: start and end of the time window, in seconds relative to the
        trace start
    :rtype: float, float
    """
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
        t0_env = times[env > 0.1 * env_max][0]
        t0 = min(t0_p, t0_env)
    if t1 is None:
        t1 = times[env > 0.3 * env_max][-1]
    return t0, t1


def _is_average(trace):
    """
    Return whether a trace is the average (template) trace of a family.

    :param trace: trace to test
    :type trace: obspy.Trace
    :return: True if the trace is the family average
    :rtype: bool
    """
    return 'average' in trace.stats.evid


def _event_info_text(trace):
    """
    Return the text with the event id, magnitude and coordinates.

    :param trace: trace of the event
    :type trace: obspy.Trace
    :return: info text
    :rtype: str
    """
    mag_str = (
        f'{trace.stats.mag_type} {trace.stats.mag:.1f}'
        if trace.stats.mag else ''
    )
    return f'{trace.stats.evid} {mag_str}\n{_coordinates_text(trace)}'


def _coordinates_text(trace):
    """
    Return the text with the coordinates and depth of a trace.

    :param trace: trace of the event
    :type trace: obspy.Trace
    :return: coordinates text
    :rtype: str
    """
    return (
        f'{trace.stats.ev_lon:.4f}°E {trace.stats.ev_lat:.4f}°N '
        f'{trace.stats.ev_depth:.3f} km'
    )


def _time_zoom(fig, ax, zoom_level):
    """
    Zoom the time axis of a family plot.

    :param fig: figure containing the plot
    :type fig: matplotlib.figure.Figure
    :param ax: axes to zoom
    :type ax: matplotlib.axes.Axes
    :param zoom_level: factor by which the time span is multiplied
    :type zoom_level: float
    """
    xmin, xmax = ax.get_xlim()
    xmean = 0.5 * (xmin + xmax)
    xspan = (xmax - xmin) * zoom_level
    ax.set_xlim(xmean - 0.5 * xspan, xmean + 0.5 * xspan)
    fig.canvas.draw_idle()


def _pan_plot(fig, ax, amount):
    """
    Pan the time axis of a family plot.

    :param fig: figure containing the plot
    :type fig: matplotlib.figure.Figure
    :param ax: axes to pan
    :type ax: matplotlib.axes.Axes
    :param amount: amount to pan, in seconds
    :type amount: float
    """
    xlim = ax.get_xlim()
    ax.set_xlim(xlim[0] + amount, xlim[1] + amount)
    fig.canvas.draw_idle()


def _plot_family(family):
    """Plot the traces of a family as wiggles, one per event."""
    try:
        st = get_family_aligned_waveforms_and_template(family)
    except NoWaveformError as msg:
        logger.error(msg)
        return
    st = process_waveforms(st)
    tr0 = st[0]
    t0, t1 = _time_limits(st)
    st.sort()
    ntraces = len(st)
    labeled_rows = set(_labeled_rows(ntraces, _max_labels()))
    _warn_if_max_labels_ignored(family, len(labeled_rows))
    if len(labeled_rows) < ntraces:
        amplitude = _trace_amplitude(ntraces)
        unlabeled_alpha = _unlabeled_alpha(ntraces, len(labeled_rows))
        labeled_linewidth = LABELED_LINEWIDTH
    else:
        amplitude = BASE_AMPLITUDE
        unlabeled_alpha = UNLABELED_ALPHA
        labeled_linewidth = DEFAULT_LINEWIDTH

    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    tracelines = []
    p_bars = []
    s_bars = []
    for n, tr in enumerate(st):
        average_trace = _is_average(tr)
        # when every trace is labeled, labeled_rows covers them all
        labeled = average_trace or n in labeled_rows
        # Normalize trace between t0 and t1
        tt0 = tr.stats.starttime + t0
        tt1 = tr.stats.starttime + t1
        tr2 = tr.copy().trim(tt0, tt1)
        tr.data /= abs(tr2.max())
        tr.detrend('demean')
        tr.data *= amplitude
        # substract t0, so that time axis starts at 0
        if not labeled:
            color = UNLABELED_COLOR
            linewidth = UNLABELED_LINEWIDTH
            alpha = unlabeled_alpha
            zorder = 1
        else:
            color = AVERAGE_COLOR if average_trace else 'black'
            linewidth = labeled_linewidth
            alpha = 1
            zorder = 2
        l, = ax.plot(
            tr.times() - t0,
            tr.data + n,
            color=color,
            linewidth=linewidth,
            alpha=alpha,
            zorder=zorder,
        )
        tracelines.append(l)
        if not labeled:
            continue
        p_arrival = tr.stats.P_arrival_time - tr.stats.starttime - t0
        s_arrival = tr.stats.S_arrival_time - tr.stats.starttime - t0
        hh = 0.3 * amplitude  # pick line half-height
        p_bar, = ax.plot(
            (p_arrival, p_arrival), (n - hh, n + hh), color='g', zorder=2)
        s_bar, = ax.plot(
            (s_arrival, s_arrival), (n - hh, n + hh), color='r', zorder=2)
        p_bars.append(p_bar)
        s_bars.append(s_bar)
        trans = ax.get_yaxis_transform()
        if average_trace:
            y_label = 'average'
            info_text = _coordinates_text(tr)
        else:
            y_label = tr.stats.orig_time.strftime('%Y-%m-%d\n%H:%M:%S')
            info_text = _event_info_text(tr)
        ax.text(
            -0.01, n, y_label, transform=trans, ha='right', va='center',
            color=color, fontsize=LABEL_FONTSIZE, linespacing=1.5)
        txt = ax.text(
            0.01, n + 0.2, info_text, transform=trans,
            color=color, fontsize=LABEL_FONTSIZE, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        if not average_trace:
            text = f'CC mean {tr.stats.cc_mean:.2f}'
            txt = ax.text(
                0.98, n + 0.2, text, ha='right',
                color=color, transform=trans, fontsize=LABEL_FONTSIZE)
            txt.set_path_effects(
                [PathEffects.withStroke(linewidth=3, foreground='w')])
    legend = ax.legend(
        [p_bars[-1], s_bars[-1]], ['P theo', 'S theo'], loc='lower right')
    legend.set_visible(False)
    for ps_bar in p_bars + s_bars:
        ps_bar.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(0, t1 - t0)
    ax.set_xlabel('Time (s)')
    title = f'Family {family.number} | {len(st) - 1} events'
    # a smaller font is needed when the labeling hint makes the title longer
    title_kwargs = {}
    if len(labeled_rows) < ntraces:
        step = round((ntraces - 1) / (len(labeled_rows) - 1))
        title += f' | labeled every {_ordinal(step)}'
        title_kwargs['fontsize'] = 10
    ax.set_title(title, loc='left', **title_kwargs)
    fig.canvas.manager.set_window_title(title)
    title = (
        f'{tr0.id} | {tr0.stats.distance:.1f} km | '
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f} Hz'
    )
    ax.set_title(title, loc='right', **title_kwargs)
    figure_name = (
        f'family_{family.number}_{tr0.id}_'
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f}Hz'
    )

    def _zoom_lines(zoom_level):
        for line in tracelines:
            ydata = line.get_ydata()
            ymean = ydata.mean()
            ydata = (ydata - ymean) * zoom_level + ymean
            line.set_ydata(ydata)
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
            _pan_plot(fig, ax, 1)
        elif event.key == 'left':
            _keypress.pan_amount -= 1
            _pan_plot(fig, ax, -1)
        elif event.key == 'shift+right':
            _keypress.time_zoom_level /= 2
            _time_zoom(fig, ax, 0.5)
        elif event.key == 'shift+left':
            _keypress.time_zoom_level *= 2
            _time_zoom(fig, ax, 2)
        elif event.key == '0':
            _zoom_lines(1.0 / _keypress.zoom_level)
            _time_zoom(fig, ax, 1.0 / _keypress.time_zoom_level)
            _pan_plot(fig, ax, -_keypress.pan_amount)
            _keypress.zoom_level = 1
            _keypress.time_zoom_level = 1
            _keypress.pan_amount = 0
        elif event.key == 'a':
            _toggle_arrivals()

    _keypress.zoom_level = 1
    _keypress.time_zoom_level = 1
    _keypress.pan_amount = 0
    fig.canvas.mpl_connect('key_press_event', _keypress)
    return fig, figure_name


def plot_families():
    """Plot traces for one or more event families."""
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
        result = _plot_family(family)
        if result is None:
            continue
        fig, figure_name = result
        save_or_show_plot(fig, figure_name, show=False)
    if config.args.output == 'NO_OUTPUT':
        print('''
        Use left/right arrow keys to scroll backwards/forward in time.
        Use shift+left/shift+right to increase/decrease the time window.
        Use up/down arrow keys to increase/decrease trace amplitude.
        Press '0' to reset the view.
        Press 'a' to show/hide theoretical arrivals.
        Press 'q' to close a plot.
        ''')
        plt.show()
