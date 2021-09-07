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
from obspy import Stream, UTCDateTime
from obspy.signal.filter import envelope
from obspy.signal.util import smooth
from .catalog import RequakeEvent
from .waveforms import (
    download_and_process_waveform, get_trace_id, get_metadata, align_traces)
from .rq_setup import rq_exit


def _get_waveform_family(config, family_number):
    fp = open(config.build_families_outfile, 'r')
    reader = csv.DictReader(fp)
    st = Stream()
    for row in reader:
        if row['family_number'] != family_number:
            continue
        ev = RequakeEvent()
        ev.evid = row['evid']
        ev.orig_time = UTCDateTime(row['orig_time'])
        ev.lon = float(row['lon'])
        ev.lat = float(row['lat'])
        ev.depth = float(row['depth_km'])
        ev.mag_type = row['mag_type']
        ev.mag = float(row['mag'])
        trace_id = get_trace_id(config, ev)
        st.append(download_and_process_waveform(config, ev, trace_id))
    fp.close()
    if not st:
        msg = 'No family found with number "{}"'.format(family_number)
        raise Exception(msg)
    return st


def _plot_family(config, family_number):
    try:
        st = _get_waveform_family(config, family_number)
        align_traces(config, st)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)

    t0 = config.args.starttime
    t1 = config.args.endtime
    # Use smooth envelope amplitude  of first trace
    # to determine default time limits (if above values are None)
    tr0 = st[0]
    env = smooth(envelope(tr0.data), 200)
    env_max = env.max()
    times = tr0.times()
    if t0 is None:
        t0 = times[env > 0.1*env_max][0]
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
    ax.axes.yaxis.set_visible(False)
    ax.minorticks_on()
    ax.tick_params(which='both', top=True, labeltop=False)
    ax.tick_params(axis='x', which='both', direction='in')
    ax.set_xlim(t0, t1)
    ax.set_xlabel('Time (s)')
    title = 'Family {}'.format(family_number)
    ax.set_title(title, loc='left')
    fig.canvas.manager.set_window_title(title)
    title = '{} | {:.1f}-{:.1f} Hz'.format(
        tr0.id, config.cc_freq_min, config.cc_freq_max)
    ax.set_title(title, loc='right')


def _build_family_numbers_list(family_numbers):
    try:
        if ',' in family_numbers:
            family_numbers = family_numbers.split(',')
        elif '-' in family_numbers:
            family0, family1 = map(int, family_numbers.split('-'))
            family_numbers = map(str, range(family0, family1))
        else:
            family_numbers = [family_numbers, ]
    except Exception:
        msg = 'Unable to find family numbers: {}'.format(family_numbers)
        raise Exception(msg)
    return family_numbers


def plot_families(config):
    try:
        family_numbers = _build_family_numbers_list(
            config.args.family_numbers)
    except Exception as m:
        logger.error(str(m))
        rq_exit(1)
    get_metadata(config)
    for family_number in family_numbers:
        _plot_family(config, family_number)
    plt.show()