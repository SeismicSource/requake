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
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
from matplotlib.ticker import FuncFormatter
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
# Colormap and interpolation used to render trace amplitudes in
# heatmap mode
AMPLITUDE_CMAP = 'seismic'
AMPLITUDE_INTERPOLATION = 'bilinear'
# Color of the average (template) trace
AVERAGE_COLOR = '#cc8800'
# Bottom panel, where all the traces are stacked on top of each other,
# with the average trace drawn on top of them
AVERAGE_LINEWIDTH = 1.2
STACKED_AMPLITUDE = 1.0
STACKED_COLOR = '0.2'
STACKED_LINEWIDTH = 0.4
PANEL_MARGIN = 0.15
# Font size of the trace labels
LABEL_FONTSIZE = 8
# Default maximum number of labeled traces, when --max-labels is not given
DEFAULT_MAX_LABELS = 15
# Above this number of decimals, the colorbar labels switch to
# exponential notation, to keep them short
MAX_FIXED_DECIMALS = 3
# Maximum width, in characters, of the colorbar tick labels
MAX_LABEL_CHARS = 8


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


def _colorbar_formatter(half_span):
    """
    Return a colorbar tick label formatter.

    The number of decimals follows the color range, so that the labels
    remain meaningful when the range is changed. For very small or very
    large ranges, exponential notation is used, to keep the labels short.

    :param half_span: half of the color range
    :type half_span: float
    :return: formatter function
    :rtype: callable
    """
    decimals = 2
    if half_span > 0:
        decimals = max(2, int(np.ceil(-np.log10(half_span))) + 1)
    digits = (
        int(np.floor(np.log10(half_span))) + 1 if half_span >= 1 else 1
    )
    # sign + digits + decimal point + decimals
    exponential = (
        decimals > MAX_FIXED_DECIMALS
        or digits + decimals + 2 > MAX_LABEL_CHARS
    )

    def _format(value, _position):
        if not value:
            return '0'
        return (
            f'{value:+.1e}' if exponential
            else f'{value:+.{decimals}f}'
        )
    return _format


def _update_colorbar_labels(colorbar, image):
    """
    Update the colorbar tick label format to the current color range.

    :param colorbar: colorbar to update
    :type colorbar: matplotlib.colorbar.Colorbar
    :param image: image whose color range drives the colorbar
    :type image: matplotlib.image.AxesImage
    """
    vmin, vmax = image.get_clim()
    colorbar.ax.yaxis.set_major_formatter(
        FuncFormatter(_colorbar_formatter(0.5 * (vmax - vmin))))


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


def _build_amplitude_matrix(traces, t0, t1):
    """
    Build a matrix of normalized trace amplitudes.

    Each row of the matrix is a trace, demeaned and normalized to the
    [-1, 1] range within the [t0, t1] time window, and resampled on a
    common time axis.

    :param traces: traces, in the order of the matrix rows
    :type traces: list of obspy.Trace
    :param t0: start of the time window, in seconds relative to trace start
    :type t0: float
    :param t1: end of the time window, in seconds relative to trace start
    :type t1: float
    :return: matrix of amplitudes (one row per trace) and time axis
    :rtype: numpy.ndarray, numpy.ndarray
    """
    dt = 1.0 / traces[0].stats.sampling_rate
    nsamples = int(round((t1 - t0) / dt)) + 1
    times = t0 + np.arange(nsamples) * dt
    matrix = np.zeros((len(traces), nsamples))
    for n, tr in enumerate(traces):
        tr_times, data = _normalized_trace_data(tr, t0, t1)
        matrix[n] = np.interp(times, tr_times, data, left=0., right=0.)
    return matrix, times


def _normalized_trace_data(trace, t0, t1):
    """
    Return the times and the data of a trace, normalized in a window.

    The data is demeaned and normalized to the [-1, 1] range within the
    [t0, t1] time window. The same normalization is applied to the whole
    trace.

    :param trace: trace to normalize
    :type trace: obspy.Trace
    :param t0: start of the time window, in seconds relative to trace start
    :type t0: float
    :param t1: end of the time window, in seconds relative to trace start
    :type t1: float
    :return: times and normalized data
    :rtype: numpy.ndarray, numpy.ndarray
    """
    data = trace.data.astype(float)
    times = trace.times()
    in_window = (times >= t0) & (times <= t1)
    if not in_window.any():
        return times, data
    data = data - data[in_window].mean()
    amplitude = np.abs(data[in_window]).max()
    if amplitude:
        data = data / amplitude
    return times, data


def _is_average(trace):
    """
    Return whether a trace is the average (template) trace of a family.

    :param trace: trace to test
    :type trace: obspy.Trace
    :return: True if the trace is the family average
    :rtype: bool
    """
    return 'average' in trace.stats.evid


def _events_and_average(st):
    """
    Return the event traces and the average (template) trace.

    :param st: stream of aligned traces
    :type st: obspy.Stream
    :return: event traces and average trace (None if missing)
    :rtype: list of obspy.Trace, obspy.Trace or None
    """
    events = [tr for tr in st if not _is_average(tr)]
    averages = [tr for tr in st if _is_average(tr)]
    return events, averages[0] if averages else None


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


def _row_labels(traces, max_labels):
    """
    Return the rows of a heatmap plot that carry a label, and their labels.

    :param traces: traces, in the order of the matrix rows
    :type traces: list of obspy.Trace
    :param max_labels: maximum number of labeled rows
    :type max_labels: int
    :return: row positions and labels
    :rtype: list, list
    """
    positions = _labeled_rows(len(traces), max_labels)
    labels = [
        traces[n].stats.orig_time.strftime('%Y-%m-%d\n%H:%M:%S')
        for n in positions
    ]
    return positions, labels


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


def _family_figure(with_colorbar=False):
    """
    Create the figure of a family plot.

    The figure has a main panel and a bottom panel. The bottom panel is
    an extra column for the colorbar, when requested.

    :param with_colorbar: whether to reserve a column for the colorbar
    :type with_colorbar: bool
    :return: figure, main axes, bottom axes and colorbar axes (or None)
    :rtype: matplotlib.figure.Figure, matplotlib.axes.Axes,
        matplotlib.axes.Axes, matplotlib.axes.Axes or None
    """
    fig = plt.figure(figsize=(8, 7.5))
    if with_colorbar:
        gs = fig.add_gridspec(
            2, 2, width_ratios=(1, 0.03), height_ratios=(12, 2),
            left=0.17, right=0.87, bottom=0.07, top=0.93, hspace=0.04,
            wspace=0.03)
    else:
        gs = fig.add_gridspec(
            2, 1, height_ratios=(12, 2), left=0.17, right=0.97,
            bottom=0.07, top=0.93, hspace=0.04)
    ax = fig.add_subplot(gs[0, 0])
    ax_bottom = fig.add_subplot(gs[1, 0], sharex=ax)
    colorbar_ax = fig.add_subplot(gs[0, 1]) if with_colorbar else None
    return fig, ax, ax_bottom, colorbar_ax


def _arrival_lines(ax, trace, t0):
    """
    Draw the theoretical arrivals of a trace in the bottom panel.

    :param ax: axes to draw in
    :type ax: matplotlib.axes.Axes
    :param trace: trace whose arrivals are drawn
    :type trace: obspy.Trace
    :param t0: start of the time window, in seconds relative to trace start
    :type t0: float
    :return: P and S arrival lines
    :rtype: list
    """
    ymin = -STACKED_AMPLITUDE
    ymax = STACKED_AMPLITUDE
    artists = []
    for color, key in (('g', 'P_arrival_time'), ('r', 'S_arrival_time')):
        arrival = getattr(trace.stats, key) - trace.stats.starttime - t0
        artists.append(
            ax.vlines(arrival, ymin, ymax, color=color, linewidth=0.8))
    return artists


def _style_bottom_panel(ax, t0, t1):
    """
    Style the bottom panel and add its labels.

    :param ax: bottom axes
    :type ax: matplotlib.axes.Axes
    :param t0: start of the time window, in seconds relative to trace start
    :type t0: float
    :param t1: end of the time window, in seconds relative to trace start
    :type t1: float
    """
    ax.set_ylim(
        -STACKED_AMPLITUDE - PANEL_MARGIN,
        STACKED_AMPLITUDE + PANEL_MARGIN)
    ax.set_yticks([])
    ax.set_xlim(0, t1 - t0)
    ax.set_xlabel('Time (s)')
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    trans = ax.get_yaxis_transform()
    ax.text(
        -0.01, 0, 'stacked', transform=trans, ha='right', va='center',
        fontsize=LABEL_FONTSIZE)


def _plot_average_stacked_panel(ax, events, tr_average, t0, t1):
    """
    Plot the traces stacked one over each other, the average on top.

    :param ax: axes to draw in
    :type ax: matplotlib.axes.Axes
    :param events: traces of the family events
    :type events: list of obspy.Trace
    :param tr_average: average (template) trace, or None
    :type tr_average: obspy.Trace or None
    :param t0: start of the time window, in seconds relative to trace start
    :type t0: float
    :param t1: end of the time window, in seconds relative to trace start
    :type t1: float
    :return: average line (or None), stacked lines and arrival artists
    :rtype: matplotlib.lines.Line2D or None, list, list
    """
    alpha = _unlabeled_alpha(len(events), 0)
    stacked_lines = []
    for tr in events:
        times, data = _normalized_trace_data(tr, t0, t1)
        line, = ax.plot(
            times - t0, STACKED_AMPLITUDE * data, color=STACKED_COLOR,
            linewidth=STACKED_LINEWIDTH, alpha=alpha, zorder=1)
        stacked_lines.append(line)
    average_line = None
    arrival_artists = []
    if tr_average is not None:
        times, data = _normalized_trace_data(tr_average, t0, t1)
        average_line, = ax.plot(
            times - t0, STACKED_AMPLITUDE * data,
            color=AVERAGE_COLOR, linewidth=AVERAGE_LINEWIDTH, zorder=3)
        txt = ax.text(
            0.01, 0.97, f'average  {_coordinates_text(tr_average)}',
            transform=ax.transAxes, va='top', color=AVERAGE_COLOR,
            fontsize=LABEL_FONTSIZE)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        arrival_artists = _arrival_lines(ax, tr_average, t0)
        for artist in arrival_artists:
            artist.set_visible(False)
    _style_bottom_panel(ax, t0, t1)
    return average_line, stacked_lines, arrival_artists


def _set_family_titles(fig, ax, family, ntraces, tr0, extra='',
                       fontsize=None):
    """
    Set the titles of a family plot.

    :param fig: figure containing the plot
    :type fig: matplotlib.figure.Figure
    :param ax: main axes
    :type ax: matplotlib.axes.Axes
    :param family: family being plotted
    :type family: Family
    :param ntraces: number of traces in the plot
    :type ntraces: int
    :param tr0: first trace of the family
    :type tr0: obspy.Trace
    :param extra: text appended to the left title
    :type extra: str
    :param fontsize: title font size, or None for the default
    :type fontsize: float or None
    """
    title_kwargs = {} if fontsize is None else {'fontsize': fontsize}
    title = f'Family {family.number} | {ntraces} events{extra}'
    ax.set_title(title, loc='left', **title_kwargs)
    fig.canvas.manager.set_window_title(title)
    title = (
        f'{tr0.id} | {tr0.stats.distance:.1f} km | '
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f} Hz'
    )
    ax.set_title(title, loc='right', **title_kwargs)


def _scale_lines(lines, zoom_level, center=None):
    """
    Scale the vertical amplitude of a set of lines.

    :param lines: lines to scale
    :type lines: list of matplotlib.lines.Line2D
    :param zoom_level: factor by which the amplitude is multiplied
    :type zoom_level: float
    :param center: y value that is kept fixed; None means the line mean
    :type center: float or None
    """
    for line in lines:
        ydata = line.get_ydata()
        ycenter = ydata.mean() if center is None else center
        line.set_ydata((ydata - ycenter) * zoom_level + ycenter)


def _labeled_every_text(ntraces, nlabeled):
    """
    Return the title hint on the label interval, or an empty string.

    :param ntraces: number of traces in the plot
    :type ntraces: int
    :param nlabeled: number of labeled traces
    :type nlabeled: int
    :return: title hint
    :rtype: str
    """
    if nlabeled >= ntraces or nlabeled < 2:
        return ''
    step = round((ntraces - 1) / (nlabeled - 1))
    return f' | labeled every {_ordinal(step)}'


def _plot_family(family):
    """Plot the traces of a family, using the selected plot mode."""
    try:
        st = get_family_aligned_waveforms_and_template(family)
    except NoWaveformError as msg:
        logger.error(msg)
        return
    st = process_waveforms(st)
    tr0 = st[0]
    t0, t1 = _time_limits(st)
    if getattr(config.args, 'mode', 'wiggle') == 'heatmap':
        return _plot_family_heatmap(family, st, tr0, t0, t1)
    return _plot_family_wiggle(family, st, tr0, t0, t1)


def _plot_family_wiggle(family, st, tr0, t0, t1):
    """Plot the traces of a family as wiggles, one per event."""
    st.sort()
    events, tr_average = _events_and_average(st)
    ntraces = len(events)
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

    fig, ax, ax_bottom, _ = _family_figure()
    average_line, stacked_lines, arrival_artists = (
        _plot_average_stacked_panel(
            ax_bottom, events, tr_average, t0, t1))
    bottom_lines = stacked_lines
    if average_line is not None:
        bottom_lines = stacked_lines + [average_line]
    tracelines = []
    p_bars = []
    s_bars = []
    for n, tr in enumerate(events):
        labeled = n in labeled_rows
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
            color = 'black'
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
        p_arrival = tr.stats.P_arrival_time - tr.stats.starttime - t0
        s_arrival = tr.stats.S_arrival_time - tr.stats.starttime - t0
        hh = 0.3 * amplitude  # pick line half-height
        p_bar, = ax.plot(
            (p_arrival, p_arrival), (n - hh, n + hh), color='g', zorder=2)
        s_bar, = ax.plot(
            (s_arrival, s_arrival), (n - hh, n + hh), color='r', zorder=2)
        p_bars.append(p_bar)
        s_bars.append(s_bar)
        if not labeled:
            continue
        trans = ax.get_yaxis_transform()
        y_label = tr.stats.orig_time.strftime('%Y-%m-%d\n%H:%M:%S')
        ax.text(
            -0.01, n, y_label, transform=trans, ha='right', va='center',
            color=color, fontsize=LABEL_FONTSIZE, linespacing=1.5)
        txt = ax.text(
            0.01, n + 0.2, _event_info_text(tr), transform=trans,
            color=color, fontsize=LABEL_FONTSIZE, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        txt = ax.text(
            0.98, n + 0.2, f'CC mean {tr.stats.cc_mean:.2f}', ha='right',
            color=color, transform=trans, fontsize=LABEL_FONTSIZE)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
    if p_bars:
        legend = ax.legend(
            [p_bars[-1], s_bars[-1]], ['P theo', 'S theo'],
            loc='lower right')
        legend.set_visible(False)
    else:
        legend = None
    for ps_bar in p_bars + s_bars:
        ps_bar.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(0, t1 - t0)
    ax.tick_params(labelbottom=False)
    extra = _labeled_every_text(ntraces, len(labeled_rows))
    _set_family_titles(
        fig, ax, family, ntraces, tr0, extra=extra,
        fontsize=10 if extra else None)
    figure_name = (
        f'family_{family.number}_{tr0.id}_'
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f}Hz'
    )

    def _zoom_lines(zoom_level):
        _scale_lines(tracelines, zoom_level)
        _scale_lines(bottom_lines, zoom_level, center=0)
        fig.canvas.draw_idle()

    def _toggle_arrivals():
        _toggle_arrivals.visible = not _toggle_arrivals.visible
        for ps_bar in p_bars + s_bars + arrival_artists:
            ps_bar.set_visible(_toggle_arrivals.visible)
        if legend is not None:
            legend.set_visible(_toggle_arrivals.visible)
        fig.canvas.draw_idle()

    _toggle_arrivals.visible = False

    def _keypress(event):
        if event.key == 'up':
            _keypress.zoom_level *= 2
            _zoom_lines(2)
        elif event.key == 'down':
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


def _plot_family_heatmap(family, st, tr0, t0, t1):
    """Plot the traces of a family as a heatmap, one row per event."""
    st.sort()
    events, tr_average = _events_and_average(st)
    ntraces = len(events)
    matrix, _ = _build_amplitude_matrix(events, t0, t1)
    # fixed margins leave a constant room for the tick and colorbar
    # labels, so that the layout does not change when the color range is
    # changed; the colorbar gets its own column, so that the heatmap and
    # the bottom panel have the same width
    fig, ax, ax_bottom, colorbar_ax = _family_figure(with_colorbar=True)
    average_line, stacked_lines, bottom_arrivals = (
        _plot_average_stacked_panel(
            ax_bottom, events, tr_average, t0, t1))
    bottom_lines = stacked_lines
    if average_line is not None:
        bottom_lines = stacked_lines + [average_line]
    image = ax.imshow(
        matrix, aspect='auto', origin='upper', cmap=AMPLITUDE_CMAP,
        vmin=-1, vmax=1, extent=(0, t1 - t0, ntraces - 0.5, -0.5),
        interpolation=AMPLITUDE_INTERPOLATION,
    )
    # leave room for the labels of the first and last rows
    margin = max(0.1, 0.03 * ntraces)
    ax.set_ylim(ntraces - 0.5 + margin, -0.5 - margin)
    colorbar = fig.colorbar(image, cax=colorbar_ax)
    colorbar.set_label('Normalized amplitude')
    _update_colorbar_labels(colorbar, image)
    positions, labels = _row_labels(events, _max_labels())
    _warn_if_max_labels_ignored(family, len(positions))
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=LABEL_FONTSIZE, linespacing=1.5)
    trans = ax.get_yaxis_transform()
    for n in positions:
        tr = events[n]
        info_text = _event_info_text(tr)
        txt = ax.text(
            0.01, n, info_text, transform=trans, va='center',
            color='black', fontsize=LABEL_FONTSIZE, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
        txt = ax.text(
            0.98, n, f'CC mean {tr.stats.cc_mean:.2f}', transform=trans,
            ha='right', va='center', color='black',
            fontsize=LABEL_FONTSIZE)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
    ax.minorticks_on()
    ax.tick_params(
        which='both', top=True, labeltop=False, labelbottom=False)
    extra = _labeled_every_text(ntraces, len(positions))
    _set_family_titles(
        fig, ax, family, ntraces, tr0, extra=extra,
        fontsize=9 if extra else None)
    figure_name = (
        f'family_{family.number}_{tr0.id}_'
        f'{tr0.stats.freq_min:.1f}-{tr0.stats.freq_max:.1f}Hz_heatmap'
    )
    rows = np.arange(ntraces)
    p_arrivals = np.array(
        [tr.stats.P_arrival_time - tr.stats.starttime for tr in events]) - t0
    s_arrivals = np.array(
        [tr.stats.S_arrival_time - tr.stats.starttime for tr in events]) - t0
    arrival_artists = [
        ax.plot(
            p_arrivals, rows, linestyle='', marker='|', color='g',
            markersize=4, zorder=3)[0],
        ax.plot(
            s_arrivals, rows, linestyle='', marker='|', color='r',
            markersize=4, zorder=3)[0],
    ]
    # the arrivals of the average trace are drawn in the bottom panel
    arrival_artists.extend(bottom_arrivals)
    for artist in arrival_artists:
        artist.set_visible(False)

    def _contrast_zoom(zoom_level):
        vmin, vmax = image.get_clim()
        center = 0.5 * (vmin + vmax)
        half_span = 0.5 * (vmax - vmin) * zoom_level
        image.set_clim(center - half_span, center + half_span)
        _update_colorbar_labels(colorbar, image)
        fig.canvas.draw_idle()

    def _zoom_lines(zoom_level):
        _scale_lines(bottom_lines, zoom_level, center=0)
        fig.canvas.draw_idle()

    def _toggle_arrivals():
        visible = not arrival_artists[0].get_visible()
        for artist in arrival_artists:
            artist.set_visible(visible)
        fig.canvas.draw_idle()

    def _keypress(event):
        if event.key == 'up':
            _keypress.zoom_level *= 2
            _zoom_lines(2)
        elif event.key == 'down':
            _keypress.zoom_level /= 2
            _zoom_lines(0.5)
        elif event.key == 'shift+up':
            _keypress.contrast_level /= 2
            _contrast_zoom(0.5)
        elif event.key == 'shift+down':
            _keypress.contrast_level *= 2
            _contrast_zoom(2)
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
            _contrast_zoom(1.0 / _keypress.contrast_level)
            _time_zoom(fig, ax, 1.0 / _keypress.time_zoom_level)
            _pan_plot(fig, ax, -_keypress.pan_amount)
            _keypress.zoom_level = 1
            _keypress.contrast_level = 1
            _keypress.time_zoom_level = 1
            _keypress.pan_amount = 0
        elif event.key == 'a':
            _toggle_arrivals()

    _keypress.zoom_level = 1
    _keypress.contrast_level = 1
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
        help_lines = [
            'Use left/right arrow keys to scroll backwards/forward in time.',
            'Use shift+left/shift+right to increase/decrease the time '
            'window.',
            'Use up/down arrow keys to increase/decrease trace amplitude.',
        ]
        if getattr(config.args, 'mode', 'wiggle') == 'heatmap':
            help_lines.append(
                'Use shift+up/shift+down to increase/decrease the color '
                'scale.')
        help_lines += [
            "Press '0' to reset the view.",
            "Press 'a' to show/hide theoretical arrivals.",
            "Press 'q' to close a plot.",
        ]
        print('\n'.join(f'        {line}' for line in help_lines))
        plt.show()
