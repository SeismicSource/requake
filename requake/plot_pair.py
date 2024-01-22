# -*- coding: utf8 -*-
"""
Download and plot traces for an event pair.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import contextlib
import logging
import matplotlib as mpl
import matplotlib.pyplot as plt
from .rq_setup import rq_exit
from .catalog import get_events, read_events
from .waveforms import get_waveform_pair, process_waveforms, align_pair

logger = logging.getLogger(__name__.split('.')[-1])
# Reduce logging level for Matplotlib to avoid DEBUG messages
mpl_logger = logging.getLogger('matplotlib')
mpl_logger.setLevel(logging.WARNING)
# Make text editable in Illustrator
mpl.rcParams['pdf.fonttype'] = 42


def _download_event(config, evid):
    """Download an event based on its evid."""
    ev = None
    with contextlib.suppress(Exception):
        cat = read_events(config.scan_catalog_file)
        return [e for e in cat if e.evid == evid][0]
    for url in config.catalog_fdsn_event_urls:
        with contextlib.suppress(Exception):
            ev = get_events(url, eventid=evid)[0]
    if ev is None:
        raise Exception(f'Cannot download event: {evid}')
    return ev


def _get_pair(config):
    """Donwload a pair of events."""
    evid1 = config.args.evid1
    evid2 = config.args.evid2
    pair = []
    for evid in evid1, evid2:
        try:
            pair.append(_download_event(config, evid))
        except Exception as m:
            logger.error(str(m))
            rq_exit(1)
    return pair


def plot_pair(config):
    try:
        pair = _get_pair(config)
        st = get_waveform_pair(config, pair)
        lag, lag_sec, cc_max = align_pair(config, st[0], st[1])
        st = process_waveforms(config, st)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)
    st.normalize()
    tr1, tr2 = st
    logger.info(
        '{} {} -- lag: {} lag_sec: {:.1f} cc_max: {:.2f}'.format(
            tr1.stats.evid, tr2.stats.evid, lag, lag_sec, cc_max
        ))
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
    label1 = (
        f'{stats1.evid}, {stats1.mag_type} {stats1.mag:.1f}, '
        f'{stats1.orig_time.strftime("%Y-%m-%dT%H:%M:%S")}\n'
        f'{stats1.ev_lat:.4f}°N {stats1.ev_lon:.4f}°E '
        f'{stats1.ev_depth:.3f} km'
    )
    label2 = (
        f'{stats2.evid}, {stats2.mag_type} {stats2.mag:.1f}, '
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
