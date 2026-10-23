# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for trace labeling, amplitude and theoretical arrivals.

These are tests for the ``plot_families`` command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import contextlib
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
    config.args = Namespace(max_labels=15, output='NO_OUTPUT')
    try:
        return importlib.import_module('requake.plot.plot_families')
    finally:
        if had_args:
            config.args = previous_args
        else:
            del config.args
            config.pop('args')


plot_families_module = _plot_families_module()


DEFAULT_MAX_LABELS = 15


def _labeled_rows(ntraces, max_labels=DEFAULT_MAX_LABELS):
    """Return the labeled row positions, with a custom label limit."""
    return plot_families_module._labeled_rows(ntraces, max_labels)


def _trace_amplitude(ntraces):
    """Return the trace amplitude, using the default settings."""
    return plot_families_module._trace_amplitude(ntraces)


def _unlabeled_alpha(ntraces, max_labels=DEFAULT_MAX_LABELS):
    """Return the alpha of the unlabeled traces, using default settings."""
    nlabeled = len(_labeled_rows(ntraces, max_labels))
    return plot_families_module._unlabeled_alpha(ntraces, nlabeled)


class TestLabeledRows(unittest.TestCase):
    """Test the rows labeled in a family plot."""

    def test_small_family_labels_all_traces(self):
        """Families up to the label limit must label every trace."""
        self.assertEqual(_labeled_rows(1), [0])
        self.assertEqual(_labeled_rows(2), [0, 1])
        self.assertEqual(_labeled_rows(15), list(range(15)))

    def test_zero_label_limit_labels_all_traces(self):
        """A zero or negative label limit must label every trace."""
        self.assertEqual(_labeled_rows(7, 0), list(range(7)))
        self.assertEqual(_labeled_rows(7, -1), list(range(7)))

    def test_single_label_limit(self):
        """With a limit of one, only the last (top) trace is labeled."""
        self.assertEqual(_labeled_rows(100, 1), [99])

    def test_label_count_never_exceeds_limit(self):
        """The label limit must not be exceeded, but for adjacent labels."""
        self.assertEqual(len(_labeled_rows(22)), 15)
        self.assertEqual(len(_labeled_rows(30)), 15)
        self.assertEqual(len(_labeled_rows(119)), 15)
        self.assertEqual(len(_labeled_rows(863)), 15)
        self.assertEqual(len(_labeled_rows(100, 10)), 10)

    def test_adjacent_labels_label_all_rows(self):
        """When the labels would be adjacent, all the rows are labeled."""
        self.assertEqual(_labeled_rows(16), list(range(16)))
        self.assertEqual(_labeled_rows(21), list(range(21)))

    def test_first_and_last_rows_are_labeled(self):
        """The first row and the last (top) row must always be labeled."""
        self.assertEqual(_labeled_rows(16)[0], 0)
        self.assertEqual(_labeled_rows(16)[-1], 15)
        self.assertEqual(_labeled_rows(119)[0], 0)
        self.assertEqual(_labeled_rows(119)[-1], 118)
        self.assertEqual(_labeled_rows(863)[0], 0)
        self.assertEqual(_labeled_rows(863)[-1], 862)

    def test_rows_are_sorted_and_unique(self):
        """The labeled rows must be sorted, without duplicates."""
        self.assertEqual(_labeled_rows(16), sorted(set(_labeled_rows(16))))
        self.assertEqual(
            _labeled_rows(119), sorted(set(_labeled_rows(119))))
        self.assertEqual(
            _labeled_rows(863), sorted(set(_labeled_rows(863))))

    def test_rows_are_evenly_spaced(self):
        """The rows must be spread evenly across the plot."""
        positions = _labeled_rows(119)
        gaps = {b - a for a, b in zip(positions[:-1], positions[1:])}
        self.assertLessEqual(max(gaps) - min(gaps), 1)


class TestOrdinal(unittest.TestCase):
    """Test the ordinal strings used in the plot title."""

    def test_ordinal_suffixes(self):
        """The ordinal suffix must follow the English rules."""
        ordinal = plot_families_module._ordinal
        self.assertEqual(ordinal(1), '1st')
        self.assertEqual(ordinal(2), '2nd')
        self.assertEqual(ordinal(3), '3rd')
        self.assertEqual(ordinal(4), '4th')
        self.assertEqual(ordinal(11), '11th')
        self.assertEqual(ordinal(12), '12th')
        self.assertEqual(ordinal(13), '13th')
        self.assertEqual(ordinal(21), '21st')
        self.assertEqual(ordinal(22), '22nd')
        self.assertEqual(ordinal(23), '23rd')
        self.assertEqual(ordinal(101), '101st')
        self.assertEqual(ordinal(111), '111th')


@contextlib.contextmanager
def _max_labels_option(value):
    """Temporarily set the value of the --max-labels option."""
    had_args = 'args' in config
    previous_args = config.get('args')
    config.args = Namespace(max_labels=value)
    try:
        yield
    finally:
        if had_args:
            config.args = previous_args
        else:
            del config.args
            config.pop('args')


class TestMaxLabelsWarning(unittest.TestCase):
    """Test the warning printed when --max-labels cannot be honored."""

    def test_warning_when_limit_is_ignored(self):
        """A warning must be printed when all the traces are labeled."""
        family = Namespace(number=7)
        with _max_labels_option(15):
            with self.assertLogs(
                    plot_families_module.logger, level='WARNING') as logs:
                plot_families_module._warn_if_max_labels_ignored(family, 16)
        self.assertIn('Family 7', logs.output[0])
        self.assertIn('--max-labels', logs.output[0])

    def test_no_warning_when_limit_is_respected(self):
        """No warning must be printed when the limit is respected."""
        family = Namespace(number=7)
        with _max_labels_option(15):
            with self.assertNoLogs(
                    plot_families_module.logger, level='WARNING'):
                plot_families_module._warn_if_max_labels_ignored(family, 15)
                plot_families_module._warn_if_max_labels_ignored(family, 8)

    def test_no_warning_when_option_is_not_given(self):
        """No warning must be printed when --max-labels is not given."""
        family = Namespace(number=7)
        with _max_labels_option(None):
            with self.assertNoLogs(
                    plot_families_module.logger, level='WARNING'):
                plot_families_module._warn_if_max_labels_ignored(family, 16)

    def test_default_max_labels(self):
        """The default label limit must be used when the option is absent."""
        with _max_labels_option(None):
            self.assertEqual(
                plot_families_module._max_labels(),
                plot_families_module.DEFAULT_MAX_LABELS)
        with _max_labels_option(40):
            self.assertEqual(plot_families_module._max_labels(), 40)


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
