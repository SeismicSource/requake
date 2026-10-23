# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the heatmap mode of the ``plot_families`` command.

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
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backend_bases import KeyEvent
from obspy import Stream, Trace, UTCDateTime
from requake.config import config


def setUpModule():
    """Render the test figures with a non-interactive backend."""
    matplotlib.use('Agg')


def _plot_families_module():
    """
    Import the plot_families module.

    The plot modules read ``config.args`` at import time, so a minimal
    config is installed for the import and then restored, to avoid
    interfering with the other test modules.
    """
    had_args = 'args' in config
    previous_args = config.get('args')
    config.args = Namespace(
        mode='heatmap', max_labels=15, output='NO_OUTPUT')
    try:
        return importlib.import_module('requake.plot.plot_families')
    finally:
        if had_args:
            config.args = previous_args
        else:
            del config.args
            config.pop('args')


plot_families_module = _plot_families_module()


def _press_keys(fig, *keys):
    """Send key presses to a figure and redraw it."""
    for key in keys:
        fig.canvas.callbacks.process(
            'key_press_event', KeyEvent('key_press_event', fig.canvas, key))
    fig.canvas.draw()


@contextlib.contextmanager
def _max_labels(value):
    """Temporarily set the value of the --max-labels option."""
    previous = config.args.max_labels
    config.args.max_labels = value
    try:
        yield
    finally:
        config.args.max_labels = previous


def _make_trace(evid, data, starttime='2020-01-01T00:00:00', dt=0.01):
    """Build a trace with the stats needed by the family plots."""
    tr = Trace(data=np.asarray(data, dtype=float))
    tr.stats.sampling_rate = 1 / dt
    tr.stats.starttime = UTCDateTime(starttime)
    tr.stats.evid = evid
    tr.stats.orig_time = UTCDateTime(starttime)
    tr.stats.P_arrival_time = tr.stats.starttime + 2.0
    tr.stats.S_arrival_time = tr.stats.starttime + 3.0
    tr.stats.freq_min = 5.0
    tr.stats.freq_max = 10.0
    tr.stats.distance = 2.0
    tr.stats.cc_mean = 0.95
    tr.stats.mag = 1.0
    tr.stats.mag_type = 'Ml'
    tr.stats.ev_lon = 12.5
    tr.stats.ev_lat = 43.3
    tr.stats.ev_depth = 5.0
    return tr


def _make_traces(ndata=500):
    """Build a small stream of synthetic traces, plus a template."""
    time = np.arange(ndata) * 0.01
    traces = [
        _make_trace('ev1', np.sin(2 * np.pi * 5 * time), dt=0.01),
        _make_trace('ev2', 2 * np.sin(2 * np.pi * 5 * time), dt=0.01),
        _make_trace('ev3', np.cos(2 * np.pi * 5 * time), dt=0.01),
    ]
    template = _make_trace(
        'average01', np.sin(2 * np.pi * 5 * time), dt=0.01,
        starttime='1900-01-01T00:00:00')
    return Stream(traces + [template])


class TestBuildAmplitudeMatrix(unittest.TestCase):
    """Test the amplitude matrix built for the heatmap plot."""

    def setUp(self):
        """Build the matrix for the synthetic traces."""
        self.traces = _make_traces()
        self.t0 = 1.0
        self.t1 = 3.0
        self.matrix, self.times = \
            plot_families_module._build_amplitude_matrix(
                self.traces, self.t0, self.t1)

    def test_matrix_shape(self):
        """The matrix must have one row per trace and a common time axis."""
        self.assertEqual(self.matrix.shape[0], len(self.traces))
        self.assertGreater(self.matrix.shape[1], 1)
        self.assertEqual(self.matrix.shape[1], len(self.times))

    def test_time_axis(self):
        """The time axis must start at t0 and end close to t1."""
        self.assertAlmostEqual(self.times[0], self.t0)
        self.assertAlmostEqual(self.times[-1], self.t1)

    def test_amplitudes_are_normalized(self):
        """Every row must be normalized to the [-1, 1] range."""
        self.assertLessEqual(np.abs(self.matrix).max(), 1.0)
        row_max = np.abs(self.matrix).max(axis=1)
        self.assertTrue(np.allclose(row_max, 1.0))

    def test_traces_are_demeaned(self):
        """Every row must have a zero mean within the time window."""
        self.assertTrue(np.allclose(self.matrix.mean(axis=1), 0.0))

    def test_rows_follow_trace_order(self):
        """Row n must correspond to trace n."""
        time = self.times
        expected = np.sin(2 * np.pi * 5 * time)
        self.assertTrue(np.allclose(self.matrix[0], expected, atol=1e-3))

    def test_zero_trace(self):
        """An all-zero trace must produce an all-zero row."""
        traces = [_make_trace('ev0', np.zeros(500))]
        matrix, _ = plot_families_module._build_amplitude_matrix(
            traces, 1.0, 3.0)
        self.assertFalse(np.any(matrix))

    def test_traces_with_different_length(self):
        """Traces of different lengths must still fit the common time axis."""
        time = np.arange(500) * 0.01
        traces = [
            _make_trace('ev1', np.sin(2 * np.pi * 5 * time)),
            _make_trace('ev2', np.sin(2 * np.pi * 5 * time)[:450]),
        ]
        matrix, times = plot_families_module._build_amplitude_matrix(
            traces, 1.0, 3.0)
        self.assertEqual(matrix.shape, (2, len(times)))
        self.assertLessEqual(np.abs(matrix).max(), 1.0)


class TestRowLabels(unittest.TestCase):
    """Test the row labels of the heatmap plot."""

    def setUp(self):
        """Build the traces for the label tests."""
        self.traces = _make_traces()

    def test_all_rows_labeled(self):
        """With a label limit above the row count, every row is labeled."""
        positions, labels = plot_families_module._row_labels(
            self.traces, 15)
        self.assertEqual(positions, [0, 1, 2, 3])
        self.assertEqual(len(labels), 4)

    def test_label_limit(self):
        """The first and last rows must always be labeled."""
        positions, labels = plot_families_module._row_labels(
            self.traces, 2)
        self.assertEqual(positions, [0, 3])
        self.assertEqual(len(labels), 2)

    def test_labels_are_origin_times(self):
        """Every label must show the origin time of the corresponding row."""
        _, labels = plot_families_module._row_labels(self.traces[:2], 15)
        self.assertEqual(labels[0], '2020-01-01\n00:00:00')
        self.assertEqual(labels[1], '2020-01-01\n00:00:00')


class TestColorbarFormatter(unittest.TestCase):
    """Test the colorbar tick label formatter."""

    def test_zero_is_labeled_zero(self):
        """Zero must not be written with a sign."""
        self.assertEqual(
            plot_families_module._colorbar_formatter(1.0)(0.0, 0), '0')

    def test_fixed_notation_for_moderate_range(self):
        """A moderate color range must use fixed notation."""
        formatter = plot_families_module._colorbar_formatter(1.0)
        self.assertEqual(formatter(1.0, 0), '+1.00')
        self.assertEqual(formatter(-0.5, 0), '-0.50')
        formatter = plot_families_module._colorbar_formatter(1e3)
        self.assertEqual(formatter(1e3, 0), '+1000.00')
        self.assertEqual(formatter(-5e2, 0), '-500.00')

    def test_exponential_notation_for_small_range(self):
        """A small color range must use exponential notation."""
        formatter = plot_families_module._colorbar_formatter(1e-4)
        self.assertEqual(formatter(1e-4, 0), '+1.0e-04')
        self.assertEqual(formatter(-5e-5, 0), '-5.0e-05')

    def test_exponential_notation_for_large_range(self):
        """A large color range must use exponential notation."""
        formatter = plot_families_module._colorbar_formatter(1e5)
        self.assertEqual(formatter(1e5, 0), '+1.0e+05')
        self.assertEqual(formatter(-5e4, 0), '-5.0e+04')

    def test_labels_stay_short(self):
        """The colorbar labels must stay short at any color range."""
        # fixed notation, capped at 6 characters
        self.assertLessEqual(
            len(plot_families_module._colorbar_formatter(1.0)(1.0, 0)), 6)
        self.assertLessEqual(
            len(plot_families_module._colorbar_formatter(0.01)(0.01, 0)), 6)
        # exponential notation, used for very small or very large ranges
        self.assertLessEqual(
            len(plot_families_module._colorbar_formatter(1e-6)(1e-6, 0)), 8)
        self.assertLessEqual(
            len(plot_families_module._colorbar_formatter(1e12)(1e12, 0)), 8)


class TestPlotFamilyHeatmap(unittest.TestCase):
    """Smoke test for the heatmap rendering."""

    def setUp(self):
        """Install a config with the options read by the plot function."""
        self.had_args = 'args' in config
        self.previous_args = config.get('args')
        config.args = Namespace(
            mode='heatmap', max_labels=15, output='NO_OUTPUT')

    def tearDown(self):
        """Close the figures and restore the config."""
        plt.close('all')
        if self.had_args:
            config.args = self.previous_args
        else:
            del config.args
            config.pop('args')

    def test_plot_returns_figure_and_name(self):
        """Plotting a family must return a figure and a file name."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, figure_name = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        self.assertIsInstance(fig, plt.Figure)
        self.assertTrue(figure_name.endswith('_heatmap'))

    def test_heatmap_axes_content(self):
        """The heatmap must contain an image and the row labels."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        ax = fig.axes[0]
        self.assertEqual(len(ax.get_images()), 1)
        self.assertEqual(len(ax.get_yticks()), len(st) - 1)

    def test_average_trace_is_not_in_the_matrix(self):
        """The average trace must be excluded from the heatmap rows."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        image = fig.axes[0].get_images()[0]
        self.assertEqual(image.get_array().shape[0], len(st) - 1)

    def test_max_labels_sets_the_number_of_labels(self):
        """--max-labels must limit the number of labeled rows."""
        family = Namespace(number=1)
        st = _make_traces()
        with _max_labels(2):
            fig, _ = plot_families_module._plot_family_heatmap(
                family, st, st[0], 1.0, 3.0)
        ax = fig.axes[0]
        # a label (date/time, info, CC mean) for the rows 0 and 2
        self.assertEqual(len(ax.get_yticks()), 2)
        self.assertEqual(len(ax.texts), 4)

    def test_max_labels_zero_labels_all_rows(self):
        """With --max-labels 0, every row must be labeled."""
        family = Namespace(number=1)
        st = _make_traces()
        with _max_labels(0):
            fig, _ = plot_families_module._plot_family_heatmap(
                family, st, st[0], 1.0, 3.0)
        ax = fig.axes[0]
        self.assertEqual(len(ax.get_yticks()), len(st) - 1)

    def test_average_label_style(self):
        """The average label must use the average trace color."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        bottom_ax = fig.axes[1]
        labels = [
            text for text in bottom_ax.texts
            if text.get_text().startswith('average')]
        self.assertEqual(len(labels), 1)
        self.assertEqual(
            labels[0].get_color(), plot_families_module.AVERAGE_COLOR)
        self.assertEqual(labels[0].get_fontsize(), 8)

    def test_layout_is_stable_when_the_contrast_changes(self):
        """Changing the color range must not move the panels."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        fig.canvas.draw()
        heatmap_pos = fig.axes[0].get_position().bounds
        template_pos = fig.axes[1].get_position().bounds
        _press_keys(fig, 'up', 'up', 'up', 'up')
        self.assertEqual(fig.axes[0].get_position().bounds, heatmap_pos)
        self.assertEqual(fig.axes[1].get_position().bounds, template_pos)
        _press_keys(fig, 'down', 'down', 'down', 'down')
        self.assertEqual(fig.axes[0].get_position().bounds, heatmap_pos)
        self.assertEqual(fig.axes[1].get_position().bounds, template_pos)

    def test_colorbar_label_fits_in_the_figure(self):
        """The colorbar label must not be clipped in an interactive window."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        colorbar_ax = fig.axes[2]
        label_extent = colorbar_ax.yaxis.label.get_window_extent(renderer)
        self.assertLessEqual(label_extent.x1, fig.bbox.width)

    def test_heatmap_and_average_panels_have_same_width(self):
        """The two panels must be aligned horizontally."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        heatmap_pos = fig.axes[0].get_position()
        template_pos = fig.axes[1].get_position()
        self.assertAlmostEqual(
            heatmap_pos.x0, template_pos.x0, places=6)
        self.assertAlmostEqual(
            heatmap_pos.width, template_pos.width, places=6)

    def test_average_trace_is_drawn_as_wiggle(self):
        """The average trace must be a line in the bottom axes."""
        family = Namespace(number=1)
        st = _make_traces()
        fig, _ = plot_families_module._plot_family_heatmap(
            family, st, st[0], 1.0, 3.0)
        bottom_ax = fig.axes[1]
        average_lines = [
            line for line in bottom_ax.get_lines()
            if line.get_color() == plot_families_module.AVERAGE_COLOR]
        self.assertEqual(len(average_lines), 1)
        self.assertEqual(
            average_lines[0].get_linewidth(),
            plot_families_module.AVERAGE_LINEWIDTH)


if __name__ == '__main__':
    unittest.main()
