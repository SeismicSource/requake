# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Download and plot traces for an event pair.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from ..config.rq_setup import rq_exit
from ..catalog.catalog import fix_non_locatable_events, read_stored_catalog
from ..waveforms.waveforms import (
    get_waveform_pair, process_waveforms, align_pair)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def _get_pair(config):
    """
    Get a pair of events, whose evid is defined in the arguments.

    :param config: Configuration object.
    :type config: requake.configobj.ConfigObj
    :return: A pair of events.
    :rtype: list

    :raises ValueError: If an event is not found in the catalog.
    :raises ValueError: If an error occurs while reading the catalog.
    :raises FileNotFoundError: If the catalog file is not found.
    """
    catalog = read_stored_catalog(config)
    fix_non_locatable_events(catalog, config)
    evid1 = config.args.evid1
    evid2 = config.args.evid2
    pair = []
    for evid in evid1, evid2:
        found_events = [e for e in catalog if e.evid == evid]
        if not found_events:
            raise ValueError(f'Event {evid} not found in catalog')
        pair.append(found_events[0])
    return pair


def plot_pair(config):
    """
    Download and plot traces for an event pair.

    :param config: Configuration object.
    :type config: requake.configobj.ConfigObj
    """
    try:
        pair = _get_pair(config)
        st = get_waveform_pair(config, pair)
        lag, lag_sec, cc_max = align_pair(config, st[0], st[1])
        st = process_waveforms(config, st)
    except Exception as m:
        logger.error(m)
        rq_exit(1)
    st.normalize()
    tr1, tr2 = st
    logger.info(
        f'{tr1.stats.evid} {tr2.stats.evid} -- '
        f'lag: {lag} lag_sec: {lag_sec:.1f} cc_max: {cc_max:.2f}'
    )
    fig, ax = plt.subplots(
        2, 1, figsize=(12, 6), sharex=True, sharey=True)
    title = f'{tr1.stats.evid}-{tr2.stats.evid}'
    fig.canvas.manager.set_window_title(title)
    title = f'{tr1.stats.evid}-{tr2.stats.evid} CC: {cc_max:.2f}'
    ax[0].set_title(title, loc='left')
    title = f'{tr1.id} | {config.cc_freq_min:.1f}-{config.cc_freq_max:.1f} Hz'
    ax[0].set_title(title, loc='right')
    stats1 = tr1.stats
    stats2 = tr2.stats
    if stats1.mag is not None:
        mag1_str = f'{stats1.mag_type} {stats1.mag:.1f}'
    else:
        mag1_str = 'no mag'
    if stats2.mag is not None:
        mag2_str = f'{stats2.mag_type} {stats2.mag:.1f}'
    else:
        mag2_str = 'no mag'
    label1 = (
        f'{stats1.evid}, {mag1_str}, '
        f'{stats1.orig_time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
        f'{stats1.ev_lat:.4f}°N {stats1.ev_lon:.4f}°E '
        f'{stats1.ev_depth:.3f} km'
    )
    label2 = (
        f'{stats2.evid}, {mag2_str}, '
        f'{stats2.orig_time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
        f'{stats2.ev_lat:.4f}°N {stats2.ev_lon:.4f}°E '
        f'{stats2.ev_depth:.3f} km'
    )
    lw = 0.8  # linewidth
    data1 = tr1.data
    data2 = tr2.data
    ax[0].plot(tr2.times(), data2, color='gray', lw=lw, label=stats2.evid)
    ax[0].plot(tr1.times(), data1, color='blue', lw=lw, label=label1)
    ax[1].plot(tr1.times(), data1, color='gray', lw=lw, label=stats1.evid)
    ax[1].plot(tr2.times(), data2, color='blue', lw=lw, label=label2)
    ax[1].set_xlabel('Time (s)')
    for _ax in ax:
        _ax.set(ylim=[-1, 1], ylabel='Normalized amplitude')
        _ax.minorticks_on()
        _ax.yaxis.set_tick_params(which='minor', bottom=False)
        _ax.grid(True)
        _ax.legend(loc='upper right')
    plt.show()
