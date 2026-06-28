# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for multi-peak template detection in scan_templates.

A synthetic template is injected at known times into a continuous trace and
the scan is expected to recover one detection per injection.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import importlib
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from obspy import Trace, UTCDateTime
from obspy.core.util import AttribDict
from requake.config import config

st = importlib.import_module('requake.scan.scan_templates')

FS = 100.0
TEMPLATE_LEN_S = 4.0
DATA_LEN_S = 600.0
DATA_START = UTCDateTime('2020-01-01T00:00:00')


def _wavelet():
    """A short band-limited wavelet (about 5 Hz)."""
    t = np.arange(int(TEMPLATE_LEN_S * FS)) / FS
    return np.sin(2 * np.pi * 5.0 * t) * np.hanning(t.size)


def _make_template():
    """Synthetic template trace with a P pick and dummy SAC geometry."""
    tr = Trace(data=_wavelet().astype(np.float64))
    tr.stats.sampling_rate = FS
    tr.stats.network, tr.stats.station = 'XX', 'TEST'
    tr.stats.location, tr.stats.channel = '00', 'BHZ'
    tr.stats.starttime = UTCDateTime('1970-01-01T00:00:00')
    tr.stats.family_number = 0
    tr.stats.sac = AttribDict({
        'a': 1.0, 'stla': 0.0, 'stlo': 0.0,
        'evla': 1.0, 'evlo': 1.0, 'evdp': 10.0,
    })
    return tr


def _make_continuous(inject_times, amplitude=1.0):
    """Continuous low-noise trace with the wavelet injected at given times."""
    wavelet = _wavelet() * amplitude
    n = int(DATA_LEN_S * FS)
    data = np.random.default_rng(0).normal(0.0, 0.01, n)
    for t_inject in inject_times:
        i0 = int(t_inject * FS)
        data[i0:i0 + wavelet.size] += wavelet
    tr = Trace(data=data.astype(np.float64))
    tr.stats.sampling_rate = FS
    tr.stats.network, tr.stats.station = 'XX', 'TEST'
    tr.stats.location, tr.stats.channel = '00', 'BHZ'
    tr.stats.starttime = DATA_START
    return tr


class TestMultiPeakDetection(unittest.TestCase):
    """scan_templates detects every peak above the threshold in a chunk."""

    def _run(self, continuous, t_min=10.0, decim_factor=1):
        """Run _scan_family_template on the given continuous trace."""
        template = _make_template()
        st.trace_cache.clear()
        fake_arrivals = (
            SimpleNamespace(time=1.0), SimpleNamespace(time=2.0), 0.0, 0.0)
        with patch.multiple(
            config, create=True,
            template_cc_min=0.5,
            template_cc_min_combined=0.4,
            template_ccs_min_combined=0.7,
            template_use_swave_cc=False,
            cc_allow_negative=False,
            t_min=t_min,
            decim_factor=decim_factor,
            time_chunk=DATA_LEN_S,
            cc_freq_min=2.0,
            cc_freq_max=10.0,
            args=Namespace(freq_band=None),
        ), patch.object(
            st, 'get_waveform_from_client',
            lambda trace_id, t0, t1: continuous.copy()
        ), patch.object(st, 'get_arrivals', lambda *a, **k: fake_arrivals):
            return st._scan_family_template(
                template, DATA_START, DATA_START + DATA_LEN_S)

    def test_two_injections_two_detections(self):
        """Two injected events give two detections at the right times."""
        detections = self._run(_make_continuous([150.0, 400.0]))
        self.assertEqual(len(detections), 2)
        for _fam, _tid, _ev, cc_max, ccs in detections:
            self.assertGreater(cc_max, 0.9)
            self.assertIsNone(ccs)
        # sac.a (1.0) equals the fake P travel time (1.0), so the recovered
        # origin time offset equals the injection time.
        offsets = sorted(
            float(ev.orig_time - DATA_START)
            for _f, _t, ev, _c, _s in detections
        )
        self.assertAlmostEqual(offsets[0], 150.0, delta=1.0)
        self.assertAlmostEqual(offsets[1], 400.0, delta=1.0)

    def test_t_min_merges_close_peaks(self):
        """A large t_min keeps only one detection among close peaks."""
        detections = self._run(
            _make_continuous([150.0, 400.0]), t_min=400.0)
        self.assertEqual(len(detections), 1)

    def test_decimation_still_detects(self):
        """Decimation by 2 still recovers both injected events."""
        detections = self._run(
            _make_continuous([150.0, 400.0]), decim_factor=2)
        self.assertEqual(len(detections), 2)
        for _fam, _tid, _ev, cc_max, _ccs in detections:
            self.assertGreater(cc_max, 0.85)

    def test_no_event_no_detection(self):
        """Pure noise yields no detection."""
        n = int(DATA_LEN_S * FS)
        tr = Trace(data=np.random.default_rng(1).normal(0.0, 0.01, n))
        tr.stats.sampling_rate = FS
        tr.stats.network, tr.stats.station = 'XX', 'TEST'
        tr.stats.location, tr.stats.channel = '00', 'BHZ'
        tr.stats.starttime = DATA_START
        self.assertEqual(self._run(tr), [])


class TestParabolicOffset(unittest.TestCase):
    """Sub-sample peak interpolation behaves correctly."""

    def test_symmetric_peak_has_zero_offset(self):
        """A symmetric peak is not shifted."""
        self.assertEqual(
            st._parabolic_offset(np.array([0.5, 1.0, 0.5]), 1), 0.0)

    def test_skewed_peak_shifts_toward_higher_neighbour(self):
        """A higher right neighbour gives a positive sub-sample offset."""
        offset = st._parabolic_offset(np.array([0.0, 1.0, 0.5]), 1)
        self.assertGreater(offset, 0.0)
        self.assertLess(offset, 0.5)

    def test_edge_index_returns_zero(self):
        """A peak at the array edge cannot be interpolated."""
        self.assertEqual(
            st._parabolic_offset(np.array([1.0, 0.5]), 0), 0.0)


if __name__ == '__main__':
    unittest.main()
