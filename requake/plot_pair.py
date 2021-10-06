#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Download and plot traces for an event pair.

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
from .rq_setup import rq_exit
from .catalog import get_events, read_events
from .waveforms import get_waveform_pair, process_waveforms, align_pair


def _download_event(config, evid):
    """Download an event based on its evid."""
    ev = None
    try:
        cat = read_events(config.scan_catalog_file)
        ev = [e for e in cat if e.evid == evid][0]
        return ev
    except Exception:
        pass
    for url in config.catalog_fdsn_event_urls:
        try:
            ev = get_events(url, eventid=evid)[0]
        except Exception:
            pass
    if ev is None:
        raise Exception('Cannot download event: {}'.format(evid))
    return ev


def _get_pair(config):
    """Donwload a pair of events."""
    evid1 = config.args.evid1
    evid2 = config.args.evid2
    pair = list()
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
    title = '{}-{}'.format(tr1.stats.evid, tr2.stats.evid)
    fig.canvas.manager.set_window_title(title)
    title = '{}-{} CC: {:.2f}'.format(tr1.stats.evid, tr2.stats.evid, cc_max)
    ax[0].set_title(title, loc='left')
    title = '{} | {:.1f}-{:.1f} Hz'.format(
        tr1.id, config.cc_freq_min, config.cc_freq_max)
    ax[0].set_title(title, loc='right')
    stats1 = tr1.stats
    stats2 = tr2.stats
    label1 = (
        '{}, {} {:.1f}, {}\n'
        '{:.4f}°N {:.4f}°E {:.3f} km'.format(
            stats1.evid, stats1.mag_type, stats1.mag,
            stats1.orig_time.strftime('%Y-%m-%dT%H:%M:%S'),
            stats1.ev_lat, stats1.ev_lon, stats1.ev_depth)
    )
    label2 = (
        '{}, {} {:.1f}, {}\n'
        '{:.4f}°N {:.4f}°E {:.3f} km'.format(
            stats2.evid, stats2.mag_type, stats2.mag,
            stats2.orig_time.strftime('%Y-%m-%dT%H:%M:%S'),
            stats2.ev_lat, stats2.ev_lon, stats2.ev_depth)
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
