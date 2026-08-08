# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for cross-correlation with mismatched sampling rates.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
from argparse import Namespace
from unittest.mock import patch
import numpy as np
from obspy import Trace, UTCDateTime
from requake.config import config
from requake.waveforms.waveforms import process_waveforms, cc_waveform_pair


class TestCrossCorrelationResampling(unittest.TestCase):
    """Cross-correlation should handle low and mismatched sampling rates."""

    def setUp(self):
        """Patch the cross-correlation config parameters."""
        patcher = patch.multiple(
            config,
            create=True,
            cc_freq_min=2.0,
            cc_freq_max=10.0,
            cc_max_shift=1.0,
            cc_allow_negative=False,
            args=Namespace(),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_trace(self, sampling_rate, duration=6.0):
        """Build a band-limited synthetic trace at a given sampling rate."""
        npts = int(duration * sampling_rate)
        t = np.arange(npts) / sampling_rate
        data = (
            np.sin(2 * np.pi * 3.0 * t)
            + 0.7 * np.sin(2 * np.pi * 5.0 * t)
            + 0.5 * np.sin(2 * np.pi * 7.0 * t)
        )
        tr = Trace(data=data.astype('float64'))
        tr.stats.sampling_rate = sampling_rate
        tr.stats.starttime = UTCDateTime(0)
        return tr

    def test_process_waveforms_clamps_below_nyquist(self):
        """At 20 Hz the 10 Hz corner is clamped just below the Nyquist."""
        out = process_waveforms(self._make_trace(20.0))
        self.assertLess(out.stats.freq_max, 10.0)
        # A 100 Hz trace keeps the configured 10 Hz corner.
        out_fast = process_waveforms(self._make_trace(100.0))
        self.assertEqual(out_fast.stats.freq_max, 10.0)

    def test_cc_mismatched_rates_resamples_instead_of_aborting(self):
        """A 100 Hz template against 20 Hz data correlates after resampling."""
        template = self._make_trace(100.0)
        data = self._make_trace(20.0)
        result = cc_waveform_pair(data, template, mode='scan')
        self.assertEqual(len(result), 4)
        _lag, _lag_sec, cc_max, _cc_mad = result
        self.assertGreater(cc_max, 0.9)

    def test_cc_equal_rates_still_correlates(self):
        """Equal sampling rates keep correlating the same signal near 1."""
        _lag, _lag_sec, cc_max = cc_waveform_pair(
            self._make_trace(100.0), self._make_trace(100.0), mode='events'
        )
        self.assertGreater(cc_max, 0.99)


if __name__ == '__main__':
    unittest.main()
