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
import matplotlib.pyplot as plt
import matplotlib.patheffects as PathEffects
import csv
from obspy import Stream
from obspy.signal.filter import envelope
from obspy.signal.util import smooth
from .waveforms import (
    download_and_process_waveform, get_metadata, align_traces)
from .families import read_families
from .rq_setup import rq_exit


def _get_family(config, families, family_number):
    for family in families:
        if family.number != family_number:
            continue
        if not family.valid:
            msg = 'Family "{}" is flagged as not valid'.format(family_number)
            raise Exception(msg)
        if (family.endtime - family.starttime) < config.args.longerthan:
            msg = 'Family "{}" is too short'.format(family.number)
            raise Exception(msg)
        return family
    msg = 'No family found with number "{}"'.format(family_number)
    raise Exception(msg)


def _get_waveform_family(config, family):
    st = Stream()
    for ev in family:
        try:
            st += download_and_process_waveform(config, ev)
        except Exception as m:
            logger.error(str(m))
            pass
    if not st:
        msg = 'No traces found for family {}'.format(family.number)
        raise Exception(msg)
    return st


def _plot_family(config, family):
    try:
        st = _get_waveform_family(config, family)
        align_traces(config, st)
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
    for n, tr in enumerate(st):
        # Normalize trace between t0 and t1
        tt0 = tr.stats.starttime + t0
        tt1 = tr.stats.starttime + t1
        tr2 = tr.copy().trim(tt0, tt1)
        tr.data /= abs(tr2.max())
        tr.detrend('demean')
        tr.data *= 0.5
        ax.plot(tr.times(), tr.data+n, color='black', linewidth=0.5)
        if config.args.arrivals:
            P_arrival = tr.stats.P_arrival_time - tr.stats.starttime
            S_arrival = tr.stats.S_arrival_time - tr.stats.starttime
            hh = 0.15  # pick line half-height
            P_bar, = ax.plot((P_arrival, P_arrival), (n-hh, n+hh), color='g')
            S_bar, = ax.plot((S_arrival, S_arrival), (n-hh, n+hh), color='r')
        trans = ax.get_yaxis_transform()
        text = '{} {} {} {:.1f}\n'.format(
            tr.stats.evid, tr.stats.orig_time.strftime('%Y-%m-%dT%H:%M:%S'),
            tr.stats.mag_type, tr.stats.mag)
        text += '{:.4f}°E {:.4f}°N {:.3f} km'.format(
            tr.stats.ev_lon, tr.stats.ev_lat, tr.stats.ev_depth)
        txt = ax.text(
            0.01, n+0.2, text, transform=trans, fontsize=8, linespacing=1.5)
        txt.set_path_effects(
            [PathEffects.withStroke(linewidth=3, foreground='w')])
    if config.args.arrivals:
        ax.legend([P_bar, S_bar], ['P theo', 'S theo'], loc='lower right')
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(t0, t1)
    ax.set_xlabel('Time (s)')
    title = 'Family {} | {} events'.format(family.number, len(st))
    ax.set_title(title, loc='left')
    fig.canvas.manager.set_window_title(title)
    title = '{} | {:.1f} km | {:.1f}-{:.1f} Hz'.format(
        tr0.id, tr0.stats.distance, config.cc_freq_min, config.cc_freq_max)
    ax.set_title(title, loc='right')


def _build_family_number_list(config):
    family_numbers = config.args.family_numbers
    if family_numbers == 'all':
        with open(config.build_families_outfile, 'r') as fp:
            reader = csv.DictReader(fp)
            fn = sorted(set(int(row['family_number']) for row in reader))
        return fn
    try:
        if ',' in family_numbers:
            fn = map(int, family_numbers.split(','))
        elif '-' in family_numbers:
            family0, family1 = map(int, family_numbers.split('-'))
            fn = range(family0, family1)
        else:
            fn = [int(family_numbers), ]
    except Exception:
        msg = 'Unable to find family numbers: {}'.format(family_numbers)
        raise Exception(msg)
    return fn


def plot_families(config):
    try:
        family_numbers = _build_family_number_list(config)
        families = read_families(config)
        get_metadata(config)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)
    for family_number in family_numbers:
        try:
            family = _get_family(config, families, family_number)
            _plot_family(config, family)
        except Exception as m:
            logger.error(str(m))
            continue
    plt.show()
