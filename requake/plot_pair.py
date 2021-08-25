#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Download and plot a pair of events.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import matplotlib.pyplot as plt
from .rq_setup import rq_exit
from .scan_catalog import get_waveform_pair, cc_waveform_pair


def _download_event(config, evid):
    """Download an event based on its evid."""
    ev = None
    for cl in config.clients_fdsn_event:
        try:
            ev = cl.get_events(eventid=evid)[0]
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
            logging.error(str(m))
            rq_exit(1)
    return pair


def plot_pair(config):
    try:
        pair = _get_pair(config)
        st = get_waveform_pair(config, pair)
        lag, lag_sec, cc_max = cc_waveform_pair(config, st)
    except Exception as m:
        logging.error(str(m))
        rq_exit(1)
    fig, ax = plt.subplots(
        2, 1, figsize=(12, 6), sharex=True, sharey=True)
    st.normalize()
    tr1, tr2 = st
    # apply lag to trace 2
    tr2.trim(
        tr2.stats.starttime-lag_sec, endtime=tr2.stats.endtime-lag_sec)
    ax[0].plot(tr2.times(), tr2.data, color='gray')
    ax[0].plot(tr1.times(), tr1.data)
    ax[1].plot(tr1.times(), tr1.data, color='gray')
    ax[1].plot(tr2.times(), tr2.data)
    for _ax in ax:
        _ax.set(ylim=[-1, 1])
        _ax.grid(True)
    plt.show()
