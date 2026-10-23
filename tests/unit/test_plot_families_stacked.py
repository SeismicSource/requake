# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the average and stacked panel of ``plot_families``.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

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
        mode='wiggle', max_labels=15, output='NO_OUTPUT',
        starttime=None, endtime=None)
    try:
        return importlib.import_module('requake.plot.plot_families')
    finally:
        if had_args:
            config.args = previous_args
        else:
            del config.args
            config.pop('args')


plot_families_module = _plot_families_module()
AVERAGE_COLOR = plot_families_module.AVERAGE_COLOR


def _press_keys(fig, *keys):
    """Send key presses to a figure and redraw it."""
    for key in keys:
        fig.canvas.callbacks.process(
            'key_press_event', KeyEvent('key_press_event', fig.canvas, key))
    fig.canvas.draw()


def _make_trace(evid, data, starttime='2020-01-01T00:00:00', dt=0.01):
    """Build a trace with the stats needed by the family plots."""
    tr = Trace(data=np.asarray(data, dtype=float))
    tr.stats.sampling_rate = 1 / dt
    tr.stats.starttime = UTCDateTime(starttime)
    tr.stats.evid = evid
    tr.stats.orig_time = UTCDateTime(starttime)
    tr.stats.P_arrival_time = tr.stats.starttime + 1.5
    tr.stats.S_arrival_time = tr.stats.starttime + 2.5
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


def _make_stream(nevents=3):
    """Build a synthetic family stream, plus the average trace."""
    time = np.arange(500) * 0.01
    traces = [
        _make_trace(f'ev{n:02d}', np.sin(2 * np.pi * (5 + n) * time))
        for n in range(nevents)
    ]
    template = _make_trace(
        'average01', np.sin(2 * np.pi * 5 * time),
        starttime='1900-01-01T00:00:00')
    return Stream(traces + [template])


def _events_and_average(nevents=3):
    """Return the event traces and the average trace."""
    events, average = plot_families_module._events_and_average(
        _make_stream(nevents))
    return events, average


def _average_lines(ax):
    """Return the average lines drawn in an axes."""
    return [
        line for line in ax.get_lines() if line.get_color() == AVERAGE_COLOR]


class TestEventsAndAverage(unittest.TestCase):
    """Test the split between event traces and average trace."""

    def test_average_is_separated(self):
        """The average trace must not be among the event traces."""
        events, average = _events_and_average(3)
        self.assertEqual(len(events), 3)
        self.assertEqual(average.stats.evid, 'average01')

    def test_no_average(self):
        """A stream without average must return no average trace."""
        st = Stream(_events_and_average(2)[0])
        events, average = plot_families_module._events_and_average(st)
        self.assertEqual(len(events), 2)
        self.assertIsNone(average)


class TestNormalizedTraceData(unittest.TestCase):
    """Test the trace normalization used by the bottom panel."""

    def setUp(self):
        """Build a trace with a known amplitude."""
        time = np.arange(500) * 0.01
        self.trace = _make_trace('ev01', 3 * np.sin(2 * np.pi * 5 * time))

    def test_data_is_normalized(self):
        """The trace must be normalized to the [-1, 1] range."""
        _, data = plot_families_module._normalized_trace_data(
            self.trace, 1.0, 3.0)
        times = self.trace.times()
        in_window = (times >= 1.0) & (times <= 3.0)
        self.assertAlmostEqual(np.abs(data[in_window]).max(), 1.0)

    def test_data_is_demeaned(self):
        """The trace must be demeaned within the window."""
        _, data = plot_families_module._normalized_trace_data(
            self.trace, 1.0, 3.0)
        times = self.trace.times()
        in_window = (times >= 1.0) & (times <= 3.0)
        self.assertAlmostEqual(data[in_window].mean(), 0.0)

    def test_times_are_returned(self):
        """The trace times must be returned unchanged."""
        times, _ = plot_families_module._normalized_trace_data(
            self.trace, 1.0, 3.0)
        np.testing.assert_allclose(times, self.trace.times())

    def test_empty_window_is_not_normalized(self):
        """Outside the trace, the raw data must be returned."""
        _, data = plot_families_module._normalized_trace_data(
            self.trace, 100.0, 200.0)
        np.testing.assert_allclose(data, self.trace.data)


class TestBottomPanel(unittest.TestCase):
    """Test the panel with the average above the stacked traces."""

    def setUp(self):
        """Draw the panel with the synthetic traces."""
        self.events, self.average = _events_and_average(3)
        self.fig, self.ax = plt.subplots()
        (self.average_line, self.stacked_lines,
         self.arrival_artists) = (
            plot_families_module._plot_average_stacked_panel(
                self.ax, self.events, self.average, 1.0, 3.0))

    def tearDown(self):
        """Close the figures."""
        plt.close('all')

    def test_one_line_per_event(self):
        """Every event must be drawn as a line."""
        self.assertEqual(len(self.stacked_lines), len(self.events))

    def test_stacked_lines_are_faint(self):
        """The stacked traces must be thin and semi-transparent."""
        linewidths = {line.get_linewidth() for line in self.stacked_lines}
        self.assertEqual(
            linewidths, {plot_families_module.STACKED_LINEWIDTH})
        self.assertTrue(
            all(line.get_alpha() < 1 for line in self.stacked_lines))

    def test_stacked_lines_share_the_baseline(self):
        """The stacked traces must be centered on zero."""
        offsets = [abs(line.get_ydata().mean()) for line in self.stacked_lines]
        self.assertLess(max(offsets), 0.1)

    def test_stacked_lines_are_normalized(self):
        """The stacked traces must not exceed the unit amplitude."""
        maxima = [
            np.abs(line.get_ydata()).max() for line in self.stacked_lines]
        self.assertLessEqual(max(maxima), 1.0001)

    def test_average_line_style(self):
        """The average must be drawn in its color and linewidth."""
        self.assertEqual(self.average_line.get_color(), AVERAGE_COLOR)
        self.assertEqual(
            self.average_line.get_linewidth(),
            plot_families_module.AVERAGE_LINEWIDTH)

    def test_average_is_drawn_on_top_of_the_stacked_traces(self):
        """The average must be drawn over all the event traces."""
        self.assertGreater(
            self.average_line.get_zorder(),
            max(line.get_zorder() for line in self.stacked_lines))

    def test_average_is_stacked_with_the_events(self):
        """The average must share the normalized range of the events."""
        self.assertLessEqual(
            np.abs(self.average_line.get_ydata()).max(), 1.0001)
        self.assertLess(abs(self.average_line.get_ydata().mean()), 0.1)

    def test_arrivals_are_hidden_by_default(self):
        """The arrival lines must be hidden until the 'a' key is pressed."""
        self.assertEqual(len(self.arrival_artists), 2)
        visible = [artist.get_visible() for artist in self.arrival_artists]
        self.assertEqual(visible, [False, False])

    def test_arrivals_span_the_panel(self):
        """The arrivals must span the whole amplitude range."""
        low = -plot_families_module.STACKED_AMPLITUDE
        high = plot_families_module.STACKED_AMPLITUDE
        bounds = [
            (artist.get_segments()[0][:, 1].min(),
             artist.get_segments()[0][:, 1].max())
            for artist in self.arrival_artists
        ]
        np.testing.assert_allclose(bounds, [(low, high), (low, high)])

    def test_panel_labels(self):
        """The panel must carry the average and stacked labels."""
        texts = [text.get_text() for text in self.ax.texts]
        self.assertTrue(
            any(text.startswith('average') for text in texts))
        self.assertIn('stacked', texts)

    def test_no_average(self):
        """A missing average must not break the panel."""
        fig, ax = plt.subplots()
        average_line, stacked_lines, arrival_artists = (
            plot_families_module._plot_average_stacked_panel(
                ax, self.events, None, 1.0, 3.0))
        self.assertIsNone(average_line)
        self.assertEqual(len(stacked_lines), len(self.events))
        self.assertEqual(arrival_artists, [])
        plt.close(fig)


class TestStackedAlpha(unittest.TestCase):
    """Test the alpha of the stacked traces."""

    @staticmethod
    def _alpha(nevents):
        """Return the alpha of the stacked traces of a family."""
        events, average = _events_and_average(nevents)
        fig, ax = plt.subplots()
        _, stacked_lines, _ = (
            plot_families_module._plot_average_stacked_panel(
                ax, events, average, 1.0, 3.0))
        alpha = stacked_lines[0].get_alpha()
        plt.close(fig)
        return alpha

    def test_alpha_decreases_with_family_size(self):
        """The more traces, the lighter they must be drawn."""
        self.assertGreater(self._alpha(3), self._alpha(200))


class TestWiggleLayout(unittest.TestCase):
    """Test the layout of the wiggle mode."""

    def setUp(self):
        """Install a config and plot a family."""
        self.had_args = 'args' in config
        self.previous_args = config.get('args')
        config.args = Namespace(
            mode='wiggle', max_labels=15, output='NO_OUTPUT',
            starttime=None, endtime=None)
        st = _make_stream()
        self.events, self.average = \
            plot_families_module._events_and_average(st)
        self.fig, _ = plot_families_module._plot_family_wiggle(
            Namespace(number=1), st, st[0], 1.0, 3.0)

    def tearDown(self):
        """Close the figures and restore the config."""
        plt.close('all')
        if self.had_args:
            config.args = self.previous_args
        else:
            del config.args
            config.pop('args')

    def test_two_panels_share_the_time_axis(self):
        """The figure must have a wiggle panel and a bottom panel."""
        self.assertEqual(len(self.fig.axes), 2)
        self.assertIs(
            self.fig.axes[0].get_shared_x_axes().joined(
                self.fig.axes[0], self.fig.axes[1]), True)

    def test_wiggle_panel_has_the_events_only(self):
        """The average trace must not be drawn in the wiggle panel."""
        self.assertEqual(_average_lines(self.fig.axes[0]), [])
        self.assertEqual(
            len(self.fig.axes[0].get_lines()), 3 * len(self.events))

    def test_average_is_in_the_bottom_panel(self):
        """The average trace must be drawn in the bottom panel."""
        self.assertEqual(len(_average_lines(self.fig.axes[1])), 1)

    def _bottom_amplitude(self, ax):
        """Return the amplitudes of the stacked and average lines."""
        stacked = [
            line for line in ax.get_lines()
            if line.get_color() == plot_families_module.STACKED_COLOR]
        average = _average_lines(ax)
        return (
            np.abs(stacked[0].get_ydata()).max(),
            np.abs(average[0].get_ydata()).max())

    def test_amplitude_keys_scale_the_stacked_traces(self):
        """The up/down keys must scale the stacked traces."""
        bottom_ax = self.fig.axes[1]
        before = self._bottom_amplitude(bottom_ax)
        _press_keys(self.fig, 'up')
        stacked, average = self._bottom_amplitude(bottom_ax)
        self.assertAlmostEqual(stacked, 2 * before[0])
        self.assertAlmostEqual(average, 2 * before[1])
        _press_keys(self.fig, 'down', '0')
        stacked, average = self._bottom_amplitude(bottom_ax)
        self.assertAlmostEqual(stacked, before[0])
        self.assertAlmostEqual(average, before[1])

    def test_arrivals_toggle_in_both_panels(self):
        """The 'a' key must show the arrivals of both panels."""
        wiggle_ax, bottom_ax = self.fig.axes
        bottom_arrivals = bottom_ax.collections
        self.assertEqual(len(bottom_arrivals), 2)
        _press_keys(self.fig, 'a')
        visible = [artist.get_visible() for artist in bottom_arrivals]
        self.assertEqual(visible, [True, True])
        wiggle_visible = [
            line for line in wiggle_ax.get_lines() if line.get_visible()]
        self.assertEqual(len(wiggle_visible), 3 * len(self.events))


class TestHeatmapLayout(unittest.TestCase):
    """Test the layout of the heatmap mode."""

    def setUp(self):
        """Plot a family as a heatmap."""
        self.had_args = 'args' in config
        self.previous_args = config.get('args')
        config.args = Namespace(
            mode='heatmap', max_labels=15, output='NO_OUTPUT',
            starttime=None, endtime=None)
        st = _make_stream()
        self.events, self.average = \
            plot_families_module._events_and_average(st)
        self.fig, _ = plot_families_module._plot_family_heatmap(
            Namespace(number=1), st, st[0], 1.0, 3.0)

    def tearDown(self):
        """Close the figures and restore the config."""
        plt.close('all')
        if self.had_args:
            config.args = self.previous_args
        else:
            del config.args
            config.pop('args')

    def test_three_axes(self):
        """The figure must have a heatmap, a bottom panel and a colorbar."""
        self.assertEqual(len(self.fig.axes), 3)
        self.assertEqual(len(self.fig.axes[0].get_images()), 1)

    def test_bottom_panel(self):
        """The bottom panel must hold the average and the stacked traces."""
        bottom_ax = self.fig.axes[1]
        self.assertEqual(len(_average_lines(bottom_ax)), 1)
        stacked = [
            line for line in bottom_ax.get_lines()
            if line.get_color() == plot_families_module.STACKED_COLOR]
        self.assertEqual(len(stacked), len(self.events))

    def _bottom_amplitude(self):
        """Return the amplitudes of the stacked and average lines."""
        bottom_ax = self.fig.axes[1]
        stacked = [
            line for line in bottom_ax.get_lines()
            if line.get_color() == plot_families_module.STACKED_COLOR]
        average = _average_lines(bottom_ax)
        return (
            np.abs(stacked[0].get_ydata()).max(),
            np.abs(average[0].get_ydata()).max())

    def test_amplitude_keys_scale_the_bottom_traces(self):
        """The up/down keys must scale the average and stacked traces."""
        before = self._bottom_amplitude()
        _press_keys(self.fig, 'up')
        stacked, average = self._bottom_amplitude()
        self.assertAlmostEqual(stacked, 2 * before[0])
        self.assertAlmostEqual(average, 2 * before[1])
        _press_keys(self.fig, 'down', '0')
        stacked, average = self._bottom_amplitude()
        self.assertAlmostEqual(stacked, before[0])
        self.assertAlmostEqual(average, before[1])

    def test_color_scale_keys(self):
        """The shift+up/down keys must change the color scale."""
        image = self.fig.axes[0].get_images()[0]
        vmin, vmax = image.get_clim()
        _press_keys(self.fig, 'shift+up')
        expected = vmin + 0.25 * (vmax - vmin)
        self.assertAlmostEqual(image.get_clim()[0], expected)
        _press_keys(self.fig, '0')
        self.assertEqual(image.get_clim(), (vmin, vmax))


if __name__ == '__main__':
    unittest.main()
