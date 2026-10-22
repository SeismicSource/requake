# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for trace labeling and amplitude of the ``plot_families`` command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import importlib
import unittest
from argparse import Namespace
from requake.config import config


def _plot_families_module():
    """
    Import the plot_families module.

    The plot modules read ``config.args`` at import time, so a minimal
    config is installed for the import and then restored, to avoid
    interfering with the other test modules.
    """
    had_args = 'args' in config
    previous_args = config.get('args')
    config.args = Namespace(compact_above=15, output='NO_OUTPUT')
    try:
        return importlib.import_module('requake.plot.plot_families')
    finally:
        if had_args:
            config.args = previous_args
        else:
            del config.args
            config.pop('args')


plot_families_module = _plot_families_module()


def _is_compact(ntraces, compact_above):
    """Return whether the family is plotted in compact mode."""
    return plot_families_module._is_compact(ntraces, compact_above)


def _label_stride(ntraces, max_labels=None):
    """Return the labeling stride, optionally with a custom label limit."""
    if max_labels is None:
        return plot_families_module._label_stride(ntraces)
    return plot_families_module._label_stride(ntraces, max_labels)


def _trace_amplitude(ntraces):
    """Return the trace amplitude, using the default settings."""
    return plot_families_module._trace_amplitude(ntraces)


def _nlabeled(ntraces, max_labels=None):
    """Return the number of labeled traces for a given family size."""
    stride = _label_stride(ntraces, max_labels)
    return -(-ntraces // stride)


def _unlabeled_alpha(ntraces):
    """Return the alpha of the unlabeled traces, using default settings."""
    return plot_families_module._unlabeled_alpha(ntraces)


class TestLabelStride(unittest.TestCase):
    """Test the stride used to label the traces of a family plot."""

    def test_small_family_labels_all_traces(self):
        """Families up to the label limit must label every trace."""
        self.assertEqual(_label_stride(1), 1)
        self.assertEqual(_label_stride(2), 1)
        self.assertEqual(_label_stride(14), 1)
        self.assertEqual(_label_stride(15), 1)

    def test_stride_increases_with_family_size(self):
        """Above the label limit, only a subset of the traces is labeled."""
        self.assertEqual(_label_stride(16), 2)
        self.assertEqual(_label_stride(30), 2)
        self.assertEqual(_label_stride(31), 3)
        self.assertEqual(_label_stride(119), 8)
        self.assertEqual(_label_stride(863), 58)

    def test_custom_label_limit(self):
        """The label limit must be configurable."""
        self.assertEqual(_label_stride(100, 10), 10)
        self.assertEqual(_label_stride(5, 10), 1)

    def test_number_of_labels_never_exceeds_limit(self):
        """The label limit must never be exceeded."""
        self.assertLessEqual(_nlabeled(15), 15)
        self.assertLessEqual(_nlabeled(30), 15)
        self.assertLessEqual(_nlabeled(119), 15)
        self.assertLessEqual(_nlabeled(863), 15)
        self.assertLessEqual(_nlabeled(100, 10), 10)
        self.assertLessEqual(_nlabeled(17, 1), 1)


class TestIsCompact(unittest.TestCase):
    """Test the choice between full and compact family plots."""

    def test_small_family_is_not_compact(self):
        """Families up to the threshold must be fully labeled."""
        self.assertFalse(_is_compact(10, 15))
        self.assertFalse(_is_compact(15, 15))

    def test_large_family_is_compact(self):
        """Families above the threshold must be plotted in compact mode."""
        self.assertTrue(_is_compact(16, 15))
        self.assertTrue(_is_compact(119, 15))

    def test_custom_threshold(self):
        """The threshold must decide when the compact mode kicks in."""
        self.assertFalse(_is_compact(40, 40))
        self.assertTrue(_is_compact(41, 40))
        self.assertFalse(_is_compact(119, 200))

    def test_zero_threshold_disables_compact_mode(self):
        """A zero (or negative) threshold must disable the compact mode."""
        self.assertFalse(_is_compact(1000, 0))
        self.assertFalse(_is_compact(1000, -1))


class TestTraceAmplitude(unittest.TestCase):
    """Test the amplitude of the traces of a family plot."""

    def test_small_family_uses_base_amplitude(self):
        """Families up to the reference size must keep the base amplitude."""
        base_amplitude = plot_families_module.BASE_AMPLITUDE
        self.assertEqual(_trace_amplitude(1), base_amplitude)
        self.assertEqual(_trace_amplitude(10), base_amplitude)
        self.assertEqual(_trace_amplitude(35), base_amplitude)

    def test_amplitude_increases_with_family_size(self):
        """Larger families must get larger trace amplitudes."""
        self.assertAlmostEqual(_trace_amplitude(70), 1.0)
        self.assertAlmostEqual(_trace_amplitude(119), 1.7)
        self.assertLess(_trace_amplitude(35), _trace_amplitude(70))
        self.assertLess(_trace_amplitude(70), _trace_amplitude(119))
        self.assertLess(_trace_amplitude(119), _trace_amplitude(863))

    def test_amplitude_is_capped(self):
        """The trace amplitude must not exceed the maximum value."""
        max_amplitude = plot_families_module.MAX_AMPLITUDE
        self.assertEqual(_trace_amplitude(10 ** 6), max_amplitude)


class TestUnlabeledAlpha(unittest.TestCase):
    """Test the alpha of the unlabeled traces of a family plot."""

    def test_small_family_uses_base_alpha(self):
        """Few unlabeled traces must keep the base alpha."""
        base_alpha = plot_families_module.UNLABELED_ALPHA
        self.assertEqual(_unlabeled_alpha(15), base_alpha)
        self.assertEqual(_unlabeled_alpha(20), base_alpha)
        self.assertEqual(_unlabeled_alpha(60), base_alpha)

    def test_alpha_decreases_with_family_size(self):
        """The more unlabeled traces, the lighter they must be drawn."""
        self.assertGreater(_unlabeled_alpha(119), _unlabeled_alpha(300))
        self.assertGreater(_unlabeled_alpha(300), _unlabeled_alpha(863))
        self.assertGreater(_unlabeled_alpha(863), _unlabeled_alpha(2000))

    def test_alpha_bounds(self):
        """The alpha must stay within (0, base alpha]."""
        base_alpha = plot_families_module.UNLABELED_ALPHA
        self.assertGreater(_unlabeled_alpha(10 ** 5), 0)
        self.assertLessEqual(_unlabeled_alpha(16), base_alpha)


if __name__ == '__main__':
    unittest.main()
