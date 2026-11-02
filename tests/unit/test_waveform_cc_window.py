# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for trimming waveforms to the cross-correlation window.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
from unittest.mock import patch
import numpy as np
from obspy import Trace, UTCDateTime
from requake.config import config
from requake.waveforms import waveforms as waveform_module


MISSING = object()


def _make_trace(starttime, duration, p_offset):
    """
    Build a trace with a theoretical P arrival.

    :param starttime: trace start time
    :type starttime: obspy.UTCDateTime
    :param duration: trace duration, in seconds
    :type duration: float
    :param p_offset: P arrival, in seconds after the trace start
    :type p_offset: float
    :return: trace
    :rtype: obspy.Trace
    """
    delta = 0.01
    npts = int(round(duration / delta)) + 1
    tr = Trace(data=np.ones(npts))
    tr.stats.sampling_rate = 1 / delta
    tr.stats.starttime = starttime
    tr.stats.P_arrival_time = starttime + p_offset
    return tr


class TestTrimToCCWindow(unittest.TestCase):
    """Test the trimming of a trace to its cross-correlation window."""

    def setUp(self):
        """Set the scan window."""
        self.config_keys = ('cc_pre_P', 'cc_trace_length')
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }
        config['cc_pre_P'] = 1.0
        config['cc_trace_length'] = 6.0

    def tearDown(self):
        """Restore the config values modified by the tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def _trim(self, start, duration, p_offset):
        """Trim a synthetic trace to the cross-correlation window."""
        tr = _make_trace(start, duration, p_offset)
        return waveform_module._trim_to_cc_window(tr)

    def test_window_around_p_arrival(self):
        """The window starts before P and lasts cc_trace_length."""
        start = UTCDateTime('2020-01-01T00:00:00')
        out = self._trim(start, 20, 10)
        self.assertEqual(out.stats.starttime, start + 9)
        self.assertEqual(out.stats.endtime, start + 15)
        self.assertEqual(out.stats.npts, 601)
        self.assertEqual(
            out.stats.P_arrival_time, start + 10)

    def test_longer_cached_trace_is_trimmed(self):
        """A trace longer than the window is cut to the window bounds."""
        start = UTCDateTime('2020-01-01T00:00:00')
        out = self._trim(start - 30, 60, 40)
        self.assertEqual(out.stats.starttime, start + 9)
        self.assertEqual(out.stats.endtime, start + 15)
        self.assertEqual(out.stats.npts, 601)

    def test_partial_data_is_kept(self):
        """Data missing at the window edges is not an error."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 3, 1)
        out = waveform_module._trim_to_cc_window(tr)
        self.assertEqual(out.stats.starttime, start)
        self.assertEqual(out.stats.endtime, start + 3)
        self.assertEqual(out.stats.npts, 301)

    def test_pre_margin_is_kept(self):
        """Extra data before the window is kept, without moving P."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 30, 15)
        out = waveform_module._trim_to_cc_window(tr, pre_margin=2.0)
        self.assertEqual(out.stats.starttime, start + 12)
        self.assertEqual(out.stats.endtime, start + 20)
        self.assertEqual(out.stats.npts, 801)
        self.assertAlmostEqual(
            out.stats.P_arrival_time - out.stats.starttime, 3.0)
        self.assertEqual(out.stats.cc_window_start, start + 14)
        self.assertEqual(out.stats.cc_window_end, start + 20)

    def test_cc_window_copy_drops_the_pre_margin(self):
        """The cross-correlation copy must not include the pre-margin."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 30, 15)
        out = waveform_module._trim_to_cc_window(tr, pre_margin=2.0)
        cc = waveform_module._cc_window_copy(out)
        self.assertEqual(cc.stats.starttime, start + 14)
        self.assertEqual(cc.stats.endtime, start + 20)
        self.assertEqual(cc.stats.npts, 601)

    def test_post_margin_is_kept(self):
        """Extra data after the window is kept, without moving P."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 30, 15)
        out = waveform_module._trim_to_cc_window(tr, post_margin=2.0)
        self.assertEqual(out.stats.starttime, start + 14)
        self.assertEqual(out.stats.endtime, start + 22)
        self.assertEqual(out.stats.npts, 801)
        self.assertAlmostEqual(
            out.stats.P_arrival_time - out.stats.starttime, 1.0)
        self.assertEqual(out.stats.cc_window_start, start + 14)
        self.assertEqual(out.stats.cc_window_end, start + 20)

    def test_post_margin_stops_at_the_data_end(self):
        """Missing data after the window is not padded."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 20, 15)
        out = waveform_module._trim_to_cc_window(tr, post_margin=2.0)
        self.assertEqual(out.stats.starttime, start + 14)
        self.assertEqual(out.stats.endtime, start + 20)
        self.assertEqual(out.stats.npts, 601)

    def test_missing_pre_margin_is_padded(self):
        """Missing data before the window is padded with the trace mean."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 10, 1)
        out = waveform_module._trim_to_cc_window(tr, pre_margin=2.0)
        self.assertEqual(out.stats.starttime, start - 2)
        self.assertEqual(out.stats.npts, 801)
        self.assertAlmostEqual(
            out.stats.P_arrival_time - out.stats.starttime, 3.0)
        np.testing.assert_allclose(out.data[:200], 1.0)

    def test_no_data_in_window_raises(self):
        """A trace with no data in the window raises NoWaveformError."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr = _make_trace(start, 5, 100)
        with self.assertRaises(waveform_module.NoWaveformError):
            waveform_module._trim_to_cc_window(tr)


class TestAlignPairFill(unittest.TestCase):
    """The time shift must not leave a step to zero at the trace edge."""

    def setUp(self):
        """Set a cross-correlation window that fits the test traces."""
        self.config_keys = ('cc_pre_P', 'cc_trace_length')
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }
        config['cc_pre_P'] = 0.5
        config['cc_trace_length'] = 1.0

    def tearDown(self):
        """Restore the config values modified by the tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def _make_pair(self):
        """Return two traces with a linear ramp, so shifts are visible."""
        start = UTCDateTime('2020-01-01T00:00:00')
        tr1 = Trace(data=np.arange(100, dtype=float))
        tr2 = Trace(data=np.arange(100, dtype=float))
        for tr in (tr1, tr2):
            tr.stats.starttime = start
            tr.stats.sampling_rate = 100
            tr.stats.P_arrival_time = start + 1
            tr.stats.S_arrival_time = start + 2
        return tr1, tr2

    def _align(self, lag, lag_sec=0.05):
        """Align a pair with a forced lag and return the second trace."""
        tr1, tr2 = self._make_pair()
        with patch.object(
                waveform_module, 'cc_waveform_pair',
                return_value=(lag, lag_sec, 0.9)):
            waveform_module.align_pair(tr1, tr2)
        return tr2

    def test_positive_lag_fills_with_mean(self):
        """The samples added at the start must carry the trace mean."""
        tr2 = self._align(5)
        self.assertEqual(tr2.data[:5].tolist(), [49.5] * 5)
        self.assertEqual(tr2.data[-1], 94)
        self.assertEqual(len(tr2.data), 100)

    def test_negative_lag_fills_with_mean(self):
        """The samples added at the end must carry the trace mean."""
        tr2 = self._align(-5)
        self.assertEqual(tr2.data[-5:].tolist(), [49.5] * 5)
        self.assertEqual(tr2.data[0], 5)
        self.assertEqual(len(tr2.data), 100)

    def test_arrivals_are_shifted(self):
        """The theoretical arrivals must follow the applied shift."""
        tr2 = self._align(5, lag_sec=0.05)
        self.assertAlmostEqual(
            tr2.stats.P_arrival_time - tr2.stats.starttime, 1.05)
        self.assertAlmostEqual(
            tr2.stats.S_arrival_time - tr2.stats.starttime, 2.05)


if __name__ == '__main__':
    unittest.main()
