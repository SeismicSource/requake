# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the wildcard location-code fallback in get_waveform_from_client.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
from unittest.mock import patch
import numpy as np
from obspy import Trace, Stream, UTCDateTime
from obspy.clients.fdsn.header import FDSNNoDataException
from requake.config import config
from requake.waveforms import NoWaveformError
from requake.waveforms.waveforms import get_waveform_from_client

T0 = UTCDateTime('2000-06-01T00:00:00')
T1 = T0 + 60.0


class _FakeClient:
    """A client that returns data only for a wildcard or empty location."""

    def __init__(self):
        """Record the location codes that were requested."""
        self.requested_locations = []

    def get_waveforms(self, network, station, location, channel,
                      starttime, endtime):
        """Raise for location '00', return a trace otherwise."""
        self.requested_locations.append(location)
        if location == '00':
            raise FDSNNoDataException('No data')
        npts = int((endtime - starttime) * 100.0) + 1
        tr = Trace(data=np.ones(npts, dtype=np.float64))
        tr.stats.sampling_rate = 100.0
        tr.stats.network, tr.stats.station = network, station
        tr.stats.location = '' if location == '*' else location
        tr.stats.channel = channel
        tr.stats.starttime = starttime
        return Stream([tr])


class TestLocationFallback(unittest.TestCase):
    """get_waveform_from_client retries with a wildcard location on demand."""

    def _patch(self, client, fallback):
        """Point the config at the fake client and set the fallback flag."""
        return patch.multiple(
            config, create=True,
            dataselect_client=client,
            event_data_path=None,
            dataselect_location_fallback=fallback,
        )

    def test_retries_with_wildcard_when_enabled(self):
        """An exact-location miss is retried with a wildcard location."""
        client = _FakeClient()
        with self._patch(client, True):
            tr = get_waveform_from_client('XX.STA.00.BHZ', T0, T1)
        self.assertIsNotNone(tr)
        self.assertEqual(client.requested_locations, ['00', '*'])

    def test_no_retry_when_disabled(self):
        """Without the flag, a miss raises and is not retried."""
        client = _FakeClient()
        with self._patch(client, False):
            with self.assertRaises(NoWaveformError):
                get_waveform_from_client('XX.STA.00.BHZ', T0, T1)
        self.assertEqual(client.requested_locations, ['00'])

    def test_no_retry_when_location_already_empty(self):
        """An empty location code is permissive and is not retried."""
        client = _FakeClient()
        with self._patch(client, True):
            tr = get_waveform_from_client('XX.STA..BHZ', T0, T1)
        self.assertIsNotNone(tr)
        self.assertEqual(client.requested_locations, [''])


if __name__ == '__main__':
    unittest.main()
