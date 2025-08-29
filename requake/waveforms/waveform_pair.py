# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Classes to handle waveform pairs for Requake.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from collections import defaultdict
from obspy import Stream
from obspy.geodetics import gps2dist_azimuth
from obspy.taup import TauPyModel
from ..config import config
from .waveforms import get_event_waveform, NoWaveformError
from .station_metadata import get_traceid_coords, MetadataMismatchError
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class WaveformPair:
    """
    Handles retrieving waveform pairs for seismic events.

    Uses caching to optimize repeated waveform retrievals and attempts
    alternative trace IDs if the initial one fails.
    """

    def __init__(self):
        self.model = TauPyModel(model='ak135')
        self.evid1 = None
        self.skipped_evids_traceids = []
        self.tr_cache = {}
        self.trace_id_attempts = defaultdict(list)

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
        # TODO: SLOW! precompute event-to-station distances
        trace_ids = config.catalog_trace_id
        if len(trace_ids) == 1:
            # don't bother with distances
            trace_id = trace_ids[0]
            if trace_id in self.trace_id_attempts[ev.evid]:
                raise NoWaveformError(
                    f'No valid trace_id available for event {ev.evid}')
            self.trace_id_attempts[ev.evid].append(trace_id)
            return trace_id
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
        # Compute distances
        distances = {}
        for trace_id, coords in traceid_coords.items():
            distance, _, _ = gps2dist_azimuth(
                coords['latitude'], coords['longitude'], ev_lat, ev_lon
            )
            distances[trace_id] = distance
        # Sort trace_ids by proximity
        sorted_trace_ids = sorted(distances, key=distances.get)
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
        ev1 = True
        for ev in pair:
            cache_key = f'{ev.evid}_{ev.trace_id}'
            if cache_key in self.skipped_evids_traceids:
                continue
            if cache_key in self.tr_cache:
                st.append(self.tr_cache[cache_key])
                continue
            try:
                tr = get_event_waveform(ev)
                if ev1:
                    # only cache the first trace since the second one
                    # will be different at each iteration
                    self.tr_cache[cache_key] = tr
                st.append(tr)
            except NoWaveformError:
                self.skipped_evids_traceids.append(cache_key)
                logger.warning(
                    f'No waveform data for event {ev.evid} and trace_id '
                    f'{ev.trace_id}. Skipping all pairs containing this '
                    'event and trace_id.'
                )
            ev1 = False
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
        # purge cache if event1 is different from previous event1
        if self.evid1 != ev1.evid:
            self.tr_cache.clear()
            self.evid1 = ev1.evid

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
