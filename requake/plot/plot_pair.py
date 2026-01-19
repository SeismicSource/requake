# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Download and plot traces for an event pair.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from ..config import config, rq_exit
from ..catalog import fix_non_locatable_events, read_stored_catalog
from ..waveforms import (
    WaveformPair, process_waveforms, align_pair,
    NoWaveformError
)
from .plot_utils import save_or_show_plot
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42
# Reduce logging level for fontTools to avoid DEBUG messages
logging.getLogger('fontTools').setLevel(logging.WARNING)


def _get_pair():
    """
    Get a pair of events, whose evid is defined in the arguments.

    :return: A pair of events.
    :rtype: list

    :raises ValueError: If an event is not found in the catalog.
    :raises ValueError: If an error occurs while reading the catalog.
    :raises FileNotFoundError: If the catalog file is not found.
    """
    try:
        catalog = read_stored_catalog()
    except FileNotFoundError as msg:
        logger.error(msg)
        rq_exit(1)
    fix_non_locatable_events(catalog)
    evid1 = config.args.evid1
    evid2 = config.args.evid2
    pair = []
    for evid in evid1, evid2:
        found_events = [e for e in catalog if e.evid == evid]
        if not found_events:
            raise ValueError(f'Event {evid} not found in catalog')
        pair.append(found_events[0])
    return pair


def plot_pair():
    """
    Download and plot traces for an event pair.
    """
    waveform_pair = WaveformPair()
    try:
        pair = _get_pair()
        st = waveform_pair.get_waveform_pair(pair)
        lag, lag_sec, cc_max = align_pair(st[0], st[1])
        st = process_waveforms(st)
    except (ValueError, NoWaveformError) as msg:
        logger.error(msg)
        rq_exit(1)
    st.normalize()
    tr1, tr2 = st
    tr_id = tr1.id
    stats1 = tr1.stats
    stats2 = tr2.stats
    evid1 = stats1.evid
    evid2 = stats2.evid
    freq_min = stats1.freq_min
    freq_max = stats2.freq_max
    logger.info(
        f'{evid1} {evid2} -- '
        f'lag: {lag} lag_sec: {lag_sec:.1f} cc_max: {cc_max:.2f}'
    )
    fig, ax = plt.subplots(
        2, 1, figsize=(12, 6), sharex=True, sharey=True)
    title = f'{evid1}-{evid2}'
    fig.canvas.manager.set_window_title(title)
    title = f'{evid1}-{evid2} CC: {cc_max:.2f}'
    ax[0].set_title(title, loc='left')
    title = f'{tr_id} | {freq_min:.1f}-{freq_max:.1f} Hz'
    ax[0].set_title(title, loc='right')
    if stats1.mag is not None:
        mag1_str = f'{stats1.mag_type} {stats1.mag:.1f}'
    else:
        mag1_str = 'no mag'
    if stats2.mag is not None:
        mag2_str = f'{stats2.mag_type} {stats2.mag:.1f}'
    else:
        mag2_str = 'no mag'
    label1 = (
        f'{evid1}, {mag1_str}, '
        f'{stats1.orig_time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
        f'{stats1.ev_lat:.4f}°N {stats1.ev_lon:.4f}°E '
        f'{stats1.ev_depth:.3f} km'
    )
    label2 = (
        f'{evid2}, {mag2_str}, '
        f'{stats2.orig_time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
        f'{stats2.ev_lat:.4f}°N {stats2.ev_lon:.4f}°E '
        f'{stats2.ev_depth:.3f} km'
    )
    lw = 0.8  # linewidth
    data1 = tr1.data
    data2 = tr2.data
    ax[0].plot(tr2.times(), data2, color='gray', lw=lw, label=evid2)
    ax[0].plot(tr1.times(), data1, color='blue', lw=lw, label=label1)
    ax[1].plot(tr1.times(), data1, color='gray', lw=lw, label=evid1)
    ax[1].plot(tr2.times(), data2, color='blue', lw=lw, label=label2)
    ax[1].set_xlabel('Time (s)')
    for _ax in ax:
        _ax.set(ylim=[-1, 1], ylabel='Normalized amplitude')
        _ax.minorticks_on()
        _ax.yaxis.set_tick_params(which='minor', bottom=False)
        _ax.grid(True)
        _ax.legend(loc='upper right')
    plot_file_basename = (
        f'{evid1}_{evid2}_{tr_id}_{freq_min:.1f}-{freq_max:.1f}Hz'
    )
    save_or_show_plot(fig, plot_file_basename)
