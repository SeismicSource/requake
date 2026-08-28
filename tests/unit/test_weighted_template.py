# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for weighted-average template building.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>,
    Marius Yvard
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import importlib
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from obspy import Trace, Stream, UTCDateTime
from requake.config import config

wf = importlib.import_module('requake.waveforms.waveforms')


class TestWeightedTemplate(unittest.TestCase):
    """Template stacking supports an opt-in weighted average."""

    def _trace(self, data, p_off, s_off, evid='ev', weight=None):
        """Build a zero-mean trace with P/S arrivals (and optional weight)."""
        tr = Trace(data=np.array(data, dtype='float64'))
        tr.stats.sampling_rate = 1.0
        tr.stats.starttime = UTCDateTime(0)
        tr.stats.evid = evid
        tr.stats.P_arrival_time = tr.stats.starttime + p_off
        tr.stats.S_arrival_time = tr.stats.starttime + s_off
        if weight is not None:
            tr.stats.weight = weight
        return tr

    def _stack(self, traces, weighted):
        """Stack a list of traces with the given weighting mode."""
        with patch.multiple(
            config, create=True,
            weighted_template_average=weighted,
            normalize_traces_before_averaging=False,
        ):
            return wf._stack_traces(Stream([t.copy() for t in traces]))

    def test_arithmetic_mean_when_disabled(self):
        """With the flag off the stack is the plain arithmetic mean."""
        a = self._trace([1., -1., 1., -1.], 5, 10)
        b = self._trace([3., -3., 3., -3.], 6, 12)
        stack = self._stack([a, b], weighted=False)
        np.testing.assert_allclose(stack.data, [2., -2., 2., -2.])
        offset = stack.stats.P_arrival_time - stack.stats.starttime
        self.assertAlmostEqual(offset, 5.5)

    def test_weighted_mean_when_enabled(self):
        """With the flag on, unequal weights produce a weighted average."""
        a = self._trace([1., -1., 1., -1.], 5, 10, weight=1.0)
        b = self._trace([3., -3., 3., -3.], 6, 12, weight=3.0)
        stack = self._stack([a, b], weighted=True)
        np.testing.assert_allclose(stack.data, [2.5, -2.5, 2.5, -2.5])
        offset = stack.stats.P_arrival_time - stack.stats.starttime
        self.assertAlmostEqual(offset, 5.75)

    def test_equal_weights_match_arithmetic_mean(self):
        """Equal weights reproduce the arithmetic mean exactly."""
        a = self._trace([1., -1., 1., -1.], 5, 10, weight=2.0)
        b = self._trace([3., -3., 3., -3.], 6, 12, weight=2.0)
        stack = self._stack([a, b], weighted=True)
        np.testing.assert_allclose(stack.data, [2., -2., 2., -2.])


class TestTemplateWeightsFile(unittest.TestCase):
    """Manual weights are read from a file and applied by event id."""

    def test_load_weights_file(self):
        """The weights file is parsed, skipping blanks and comments."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'weights.txt')
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write('# comment\nev1 0.5\nev2 2\n\n')
            with patch.object(config, 'template_weights_file', path,
                              create=True):
                weights = wf._load_template_weights()
        self.assertEqual(weights, {'ev1': 0.5, 'ev2': 2.0})

    def test_no_file_returns_empty(self):
        """No configured file yields an empty mapping."""
        with patch.object(config, 'template_weights_file', None,
                          create=True):
            self.assertEqual(wf._load_template_weights(), {})

    def test_apply_weights_defaults_missing_to_one(self):
        """Traces absent from the file keep a weight of 1."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'weights.txt')
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write('evA 4\n')
            tr_a = Trace(data=np.zeros(2))
            tr_a.stats.evid = 'evA'
            tr_b = Trace(data=np.zeros(2))
            tr_b.stats.evid = 'evB'
            st = Stream([tr_a, tr_b])
            with patch.object(config, 'template_weights_file', path,
                              create=True):
                wf._apply_template_weights(st)
        self.assertEqual(tr_a.stats.weight, 4.0)
        self.assertEqual(tr_b.stats.weight, 1.0)


if __name__ == '__main__':
    unittest.main()
