# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Classes to handle waveform pairs for Requake.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from collections import defaultdict, OrderedDict
from obspy import Stream
from obspy.geodetics import gps2dist_azimuth
from obspy.taup import TauPyModel
from ..config import config
from .waveforms import (
    get_event_waveform,
    get_waveform_cache_stats,
    NoWaveformError,
)
from .station_metadata import get_traceid_coords, MetadataMismatchError
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class WaveformPair:
    """
    Handles retrieving waveform pairs for seismic events.

    Uses caching to optimize repeated waveform retrievals and attempts
    alternative trace IDs if the initial one fails.
    """

    def __init__(self):
        """Initialize the waveform-pair helper and its caches."""
        self.model = TauPyModel(model='ak135')
        self.evid1 = None
        self.max_trace_cache_size = max(
            int(getattr(config, 'catalog_waveform_cache_size', 5000)),
            2,
        )
        self.skipped_evids_traceids = set()
        self.tr_cache = OrderedDict()
        self.trace_id_attempts = defaultdict(list)
        self.sorted_trace_ids_cache = {}
        self.trace_cache_hits = 0
        self.trace_cache_misses = 0
        self.sorted_trace_ids_cache_hits = 0
        self.sorted_trace_ids_cache_misses = 0
        self.skipped_trace_hits = 0
        self.trace_cache_clears = 0
        self.trace_cache_evictions = 0
        self.initial_disk_cache_stats = get_waveform_cache_stats()

    def _cache_get(self, cache_key):
        """Get trace from LRU cache and mark as recently used."""
        tr = self.tr_cache.get(cache_key)
        if tr is None:
            return None
        self.tr_cache.move_to_end(cache_key)
        return tr

    def _cache_put(self, cache_key, tr):
        """Store trace in LRU cache and evict oldest if needed."""
        self.tr_cache[cache_key] = tr
        self.tr_cache.move_to_end(cache_key)
        if len(self.tr_cache) > self.max_trace_cache_size:
            self.tr_cache.popitem(last=False)
            self.trace_cache_evictions += 1

    def get_cache_stats(self):
        """Return cache hit/miss statistics."""
        trace_cache_lookups = self.trace_cache_hits + self.trace_cache_misses
        sorted_trace_id_lookups = (
            self.sorted_trace_ids_cache_hits
            + self.sorted_trace_ids_cache_misses
        )
        disk_cache_stats = get_waveform_cache_stats()
        return {
            'trace_cache_hits': self.trace_cache_hits,
            'trace_cache_misses': self.trace_cache_misses,
            'trace_cache_hit_rate': (
                self.trace_cache_hits / trace_cache_lookups
                if trace_cache_lookups > 0
                else 0.0
            ),
            'sorted_trace_ids_cache_hits': self.sorted_trace_ids_cache_hits,
            'sorted_trace_ids_cache_misses': (
                self.sorted_trace_ids_cache_misses
            ),
            'sorted_trace_ids_cache_hit_rate': (
                self.sorted_trace_ids_cache_hits / sorted_trace_id_lookups
                if sorted_trace_id_lookups > 0
                else 0.0
            ),
            'skipped_trace_hits': self.skipped_trace_hits,
            'trace_cache_clears': self.trace_cache_clears,
            'trace_cache_evictions': self.trace_cache_evictions,
            'trace_cache_size': len(self.tr_cache),
            'max_trace_cache_size': self.max_trace_cache_size,
            'disk_cache_hits': (
                disk_cache_stats['disk_cache_hits']
                - self.initial_disk_cache_stats['disk_cache_hits']
            ),
            'disk_cache_misses': (
                disk_cache_stats['disk_cache_misses']
                - self.initial_disk_cache_stats['disk_cache_misses']
            ),
            'disk_cache_writes': (
                disk_cache_stats['disk_cache_writes']
                - self.initial_disk_cache_stats['disk_cache_writes']
            ),
            'disk_cache_read_errors': (
                disk_cache_stats['disk_cache_read_errors']
                - self.initial_disk_cache_stats['disk_cache_read_errors']
            ),
            'disk_cache_write_errors': (
                disk_cache_stats['disk_cache_write_errors']
                - self.initial_disk_cache_stats['disk_cache_write_errors']
            ),
        }

    def _get_sorted_trace_ids(self, ev):
        """Return trace IDs for an event sorted by proximity."""
        cache_key = (
            ev.evid, ev.orig_time, ev.lat, ev.lon
        )
        if cache_key in self.sorted_trace_ids_cache:
            self.sorted_trace_ids_cache_hits += 1
            return self.sorted_trace_ids_cache[cache_key]
        self.sorted_trace_ids_cache_misses += 1
        ev_lat, ev_lon, orig_time = ev.lat, ev.lon, ev.orig_time
        try:
            traceid_coords = get_traceid_coords(orig_time)
        except MetadataMismatchError as err:
            logger.error(
                f'No metadata available for event {ev.evid} at {orig_time}.'
            )
            raise NoWaveformError(
                f'No valid trace_id available for event {ev.evid}'
            ) from err
        distances = {}
        for trace_id, coords in traceid_coords.items():
            distance, _, _ = gps2dist_azimuth(
                coords['latitude'], coords['longitude'], ev_lat, ev_lon
            )
            distances[trace_id] = distance
        sorted_trace_ids = tuple(sorted(distances, key=distances.get))
        self.sorted_trace_ids_cache[cache_key] = sorted_trace_ids
        return sorted_trace_ids

    def _get_trace_id(self, ev):
        """
        Get trace ID to use with the given event.

        If there is only one trace_id in the config file, return it.
        If there are multiple trace_ids, return the closest one.
        Keeps retrying with the next closest trace_id until one is found
        or all fail.

        :param ev: an Event object
        :type ev: Event
        :return: the trace_id to use
        :rtype: str

        :raises NoWaveformError: if no trace_id is available
        """
        trace_ids = config.catalog_trace_id
        if len(trace_ids) == 1:
            # don't bother with distances
            trace_id = trace_ids[0]
            if trace_id in self.trace_id_attempts[ev.evid]:
                raise NoWaveformError(
                    f'No valid trace_id available for event {ev.evid}')
            self.trace_id_attempts[ev.evid].append(trace_id)
            return trace_id
        sorted_trace_ids = self._get_sorted_trace_ids(ev)
        # Track attempts for this event
        for trace_id in sorted_trace_ids:
            if trace_id not in self.trace_id_attempts[ev.evid]:
                self.trace_id_attempts[ev.evid].append(trace_id)
                return trace_id
        raise NoWaveformError(
            f'No valid trace_id available for event {ev.evid}')

    def _get_pair_stream(self, pair):
        """
        Get a stream of waveforms for a given pair of events.

        :param pair: a pair of events
        :type pair: tuple of two Event objects
        :return: a Stream of waveforms
        :rtype: obspy.Stream

        :raises NoWaveformError: if no waveform data is available
        """
        st = Stream()
        for ev in pair:
            cache_key = f'{ev.evid}_{ev.trace_id}'
            if cache_key in self.skipped_evids_traceids:
                self.skipped_trace_hits += 1
                continue
            tr = self._cache_get(cache_key)
            if tr is not None:
                self.trace_cache_hits += 1
                st.append(tr)
                continue
            self.trace_cache_misses += 1
            try:
                tr = get_event_waveform(ev)
                self._cache_put(cache_key, tr)
                st.append(tr)
            except NoWaveformError as err:
                self.skipped_evids_traceids.add(cache_key)
                msg = str(err).replace('\n', ' ')
                logger.warning(
                    f'No waveform data for event {ev.evid} and trace_id '
                    f'{ev.trace_id}. Skipping all pairs containing this '
                    'event and trace_id.'
                    f'Error message: {msg}'
                )
        if len(st) < 2:
            raise NoWaveformError('Unable to get waveform data for pair')
        return st

    def get_waveform_pair(self, pair):
        """
        Get waveforms for a given pair of events.

        Uses caching to avoid re-fetching waveforms.
        Attempts alternative trace_ids if the first one fails.

        :param pair: a pair of events
        :type pair: tuple of two Event objects
        :return: a Stream of waveforms
        :rtype: obspy.Stream

        :raises NoWaveformError: if no waveform data is available
        """
        ev1, ev2 = pair
        # clear trace_id_attempts
        self.trace_id_attempts.clear()

        ev1.trace_id = ev2.trace_id = self._get_trace_id(ev1)
        st = None
        while True:
            try:
                st = self._get_pair_stream(pair)
                break
            except NoWaveformError:
                try:
                    ev1.trace_id = ev2.trace_id = self._get_trace_id(ev1)
                except NoWaveformError:
                    break
        if st is None:
            # die silently
            raise NoWaveformError
        return st
