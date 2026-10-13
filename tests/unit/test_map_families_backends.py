# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the map backends of the map_families command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import os
import sys
import unittest
import tempfile
import importlib
from importlib.util import find_spec
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch
from obspy import UTCDateTime
import numpy as np
import matplotlib.pyplot as plt
from requake.catalog import RequakeEvent
from requake.config import config
from requake.config.parse_arguments import parse_arguments
from requake.families.families import Family


# the folium backend is optional: skip the tests requiring it, if missing
FOLIUM_AVAILABLE = all(
    find_spec(module) is not None for module in ('folium', 'branca')
)
# config values needed to build families and to plot the map
CONFIG_VALUES = {
    'mag_to_slip_model': 'NJ1998',
    'catalog_lon_min': 9.0,
    'catalog_lon_max': 11.0,
    'catalog_lat_min': 44.0,
    'catalog_lat_max': 46.0,
}


def _map_args(**overrides):
    """Return a Namespace with the map_families command line options."""
    args = {
        'backend': 'folium',
        'output': 'NO_OUTPUT',
        'mapstyle': 'satellite',
        'apikey': None,
        'zoom': None,
        'colorby': 'depth',
        'colormap': None,
        'range': None,
        'sizeby': 'number_of_events',
    }
    args.update(overrides)
    return Namespace(**args)


def _assert_rq_exit(test_case, module, func, *args):
    """Assert that a function exits with an error, calling rq_exit(1)."""
    with patch.object(module, 'rq_exit', side_effect=SystemExit) as mocked:
        with test_case.assertRaises(SystemExit):
            func(*args)
    mocked.assert_called_once_with(1)


def _make_families():
    """Build two synthetic families for testing the map backends."""
    families = []
    families_data = (
        (1, 9.5, 44.5, 5.0, 5),
        (2, 10.2, 45.3, 25.0, 20),
    )
    for number, lon, lat, depth, nevents in families_data:
        family = Family(number)
        for index in range(nevents):
            family.append(RequakeEvent(
                evid=f'{number}_{index}',
                orig_time=UTCDateTime('2020-01-01') + index * 86400 * 30,
                lon=lon,
                lat=lat,
                depth=depth,
                mag_type='Ml',
                mag=1.0 + 0.1 * index,
                trace_id='XX.TEST.00.HHZ',
            ))
        families.append(family)
    return families


class _MapTestBase(unittest.TestCase):
    """Base class providing the config needed by the plot modules."""

    modules = {}

    @classmethod
    def setUpClass(cls):
        """Import the plot modules, with a minimal config in place."""
        cls.args = _map_args()
        config.args = cls.args
        for key, value in CONFIG_VALUES.items():
            config[key] = value
        for name in (
            'map_families', 'map_families_cartopy', 'map_families_folium'
        ):
            cls.modules[name] = importlib.import_module(f'requake.plot.{name}')


class TestMapFamiliesBackendCli(unittest.TestCase):
    """Validate argparse wiring for the map backend option."""

    def _parse(self, argv):
        with patch.object(sys, 'argv', argv):
            return parse_arguments('requake')

    def test_default_backend_is_cartopy(self):
        """The cartopy backend should be used by default."""
        args = self._parse(['requake', 'map_families'])
        self.assertEqual(args.action, 'map_families')
        self.assertEqual(args.backend, 'cartopy')

    def test_short_backend_option(self):
        """The -b/--backend option should select the folium backend."""
        args = self._parse(['requake', 'map_families', '-b', 'folium'])
        self.assertEqual(args.backend, 'folium')

    def test_invalid_backend(self):
        """An unknown backend should be rejected by argparse."""
        with self.assertRaises(SystemExit) as exc:
            self._parse(['requake', 'map_families', '-b', 'nope'])
        self.assertEqual(exc.exception.code, 2)

    def test_default_sizeby(self):
        """Markers should be scaled with the number of events by default."""
        args = self._parse(['requake', 'map_families'])
        self.assertEqual(args.sizeby, 'number_of_events')

    def test_short_sizeby_option(self):
        """The -s/--sizeby option should select the marker size quantity."""
        args = self._parse(['requake', 'map_families', '-s', 'depth'])
        self.assertEqual(args.sizeby, 'depth')

    def test_invalid_sizeby(self):
        """An unknown marker size quantity should be rejected by argparse."""
        with self.assertRaises(SystemExit) as exc:
            self._parse(['requake', 'map_families', '--sizeby', 'nope'])
        self.assertEqual(exc.exception.code, 2)


class TestMapFamiliesDispatch(_MapTestBase):
    """Test the dispatch to the map backends."""

    def test_dispatch_to_cartopy(self):
        """The cartopy backend should be called when selected."""
        families = _make_families()
        module = self.modules['map_families']
        with patch.object(
            module, 'read_selected_families', return_value=families,
        ), patch.object(
            module, 'config',
            SimpleNamespace(args=_map_args(backend='cartopy')),
        ), patch.object(
            self.modules['map_families_cartopy'],
            'plot_families_map_with_cartopy',
        ) as mocked:
            module.map_families()
        mocked.assert_called_once_with(families)

    def test_dispatch_to_folium(self):
        """The folium backend should be called when selected."""
        families = _make_families()
        module = self.modules['map_families']
        with patch.object(
            module, 'read_selected_families', return_value=families,
        ), patch.object(
            module, 'config',
            SimpleNamespace(args=_map_args(backend='folium')),
        ), patch.object(
            self.modules['map_families_folium'],
            'plot_families_map_with_folium',
        ) as mocked:
            module.map_families()
        mocked.assert_called_once_with(families)

    def test_invalid_backend(self):
        """An unknown backend should produce an error and exit."""
        module = self.modules['map_families']
        with patch.object(
            module, 'read_selected_families', return_value=_make_families(),
        ), patch.object(
            module, 'config',
            SimpleNamespace(args=_map_args(backend='nope')),
        ):
            _assert_rq_exit(self, module, module.map_families)


class TestFamilyMarkerRadii(_MapTestBase):
    """Test the marker size scaling shared by the map backends."""

    def setUp(self):
        """Build the synthetic families and import the shared helpers."""
        self.families = _make_families()
        self.utils = importlib.import_module('requake.plot.map_families_utils')

    def _radii(self, sizeby):
        """Return the marker radii, the legend and the label."""
        return self.utils.get_family_marker_radii(self.families, sizeby)

    def test_number_of_events_scale(self):
        """The default scale should be the number of events."""
        radii, legend, label = self._radii('number_of_events')
        self.assertEqual(label, 'Number of Events')
        self.assertEqual(radii, [
            self.utils.MIN_MARKER_RADIUS, self.utils.MAX_MARKER_RADIUS
        ])
        self.assertEqual(
            [radius for _value, radius in legend],
            [self.utils.MIN_MARKER_RADIUS, 9.5, self.utils.MAX_MARKER_RADIUS]
        )
        self.assertEqual([value for value, _ in legend], ['5', '12.5', '20'])

    def test_linear_scale_for_narrow_ranges(self):
        """Values spanning less than a decade should use a linear scale."""
        self.families[0].depth = 5.0
        self.families[1].depth = 25.0
        _radii, legend, label = self._radii('depth')
        self.assertEqual(label, 'Depth (km)')
        self.assertEqual([value for value, _ in legend], ['5', '15', '25'])

    def test_logarithmic_scale_for_wide_ranges(self):
        """Values spanning decades should use a logarithmic scale."""
        self.families[0].cumul_moment = 1e10
        self.families[1].cumul_moment = 1e15
        radii, legend, label = self._radii('cumul_moment')
        self.assertEqual(label, 'Cumulative Moment (N·m)')
        self.assertEqual(radii, [
            self.utils.MIN_MARKER_RADIUS, self.utils.MAX_MARKER_RADIUS
        ])
        # the middle legend entry is the geometric mean of the values
        self.assertEqual([value for value, _ in legend], ['1e+10', '3.16e+12',
                                                          '1e+15'])

    def test_missing_values_get_the_minimum_size(self):
        """Families with a missing value should get the minimum size."""
        self.families[1].slip_rate = np.inf
        radii, _legend, label = self._radii('slip_rate')
        self.assertEqual(label, 'Slip Rate (cm/y)')
        self.assertEqual(radii, [
            self.utils.MAX_MARKER_RADIUS, self.utils.MIN_MARKER_RADIUS
        ])

    def test_single_family_gets_the_maximum_size(self):
        """A single family should be plotted with the maximum size."""
        radii, legend, _label = self.utils.get_family_marker_radii(
            self.families[:1], 'number_of_events')
        self.assertEqual(radii, [self.utils.MAX_MARKER_RADIUS])
        self.assertEqual(len(legend), 1)

    def test_distance_from_scale(self):
        """The distance from a reference point should be a valid scale."""
        config.distance_from_lon = 10.0
        config.distance_from_lat = 45.0
        _radii, _legend, label = self._radii('distance_from')
        self.assertEqual(label, 'Distance from (45.0°N,10.0°E) (km)')

    def test_distance_from_without_reference_point(self):
        """A missing reference point should produce an error."""
        config.distance_from_lon = None
        config.distance_from_lat = None
        with self.assertRaises(ValueError):
            self._radii('distance_from')

    def test_invalid_sizeby(self):
        """An invalid size quantity should produce an error."""
        with self.assertRaises(ValueError):
            self._radii('invalid')


class TestFoliumBackend(_MapTestBase):
    """Test the folium map backend."""

    def setUp(self):
        """Create a temporary directory for the map output."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)
        self.families = _make_families()
        self.module = self.modules['map_families_folium']
        config.args = _map_args()

    def _out_file(self, name='family_map.html'):
        """Set and return an output file inside the temporary directory."""
        config.args.output = os.path.join(self.test_dir.name, name)
        return config.args.output

    def test_folium_not_installed(self):
        """A clear error should be raised when folium is not installed."""
        with patch.object(self.module, 'folium', None):
            _assert_rq_exit(
                self, self.module, self.module.plot_families_map_with_folium,
                self.families,
            )

    def test_image_output_format_is_rejected(self):
        """An image format should not be a valid output for folium."""
        config.args = _map_args(output='png')
        _assert_rq_exit(
            self, self.module, self.module.plot_families_map_with_folium,
            self.families,
        )

    def test_non_html_output_file_is_rejected(self):
        """An output file without an .html extension should be rejected."""
        config.args = _map_args(output='family_map.json')
        _assert_rq_exit(
            self, self.module, self.module.plot_families_map_with_folium,
            self.families,
        )

    def test_invalid_colorby_is_reported(self):
        """An invalid colorby value should produce an error and exit."""
        self._out_file()
        config.args.colorby = 'invalid'
        _assert_rq_exit(
            self, self.module, self.module.plot_families_map_with_folium,
            self.families,
        )

    def test_missing_stamen_apikey_is_reported(self):
        """The Stamen Terrain map style should require an API key."""
        self._out_file()
        config.args.mapstyle = 'stamen_terrain'
        _assert_rq_exit(
            self, self.module, self.module.plot_families_map_with_folium,
            self.families,
        )

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_map_is_written_to_file(self):
        """The HTML map should contain the markers, the popups and legend."""
        out_file = self._out_file()
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('L.circleMarker', html)
        self.assertIn('Family 2', html)
        self.assertIn('XX.TEST.00.HHZ', html)
        self.assertIn('Depth (km)', html)
        self.assertIn('2 families', html)
        self.assertIn('tickValues', html)
        # the satellite map style should be the default one
        self.assertIn('World_Imagery', html)

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_marker_size_scales_with_the_number_of_events(self):
        """The largest family should have the largest marker."""
        out_file = self._out_file()
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('"radius": 5.0', html)
        self.assertIn('"radius": 14.0', html)

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_size_legend(self):
        """The map should show a legend explaining the marker size."""
        out_file = self._out_file()
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('Number of Events', html)
        self.assertIn('>5</div>', html)
        self.assertIn('>20</div>', html)

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_time_legend_labels_are_relabeled(self):
        """Colorby time should add the JavaScript date relabeling."""
        out_file = self._out_file()
        config.args.colorby = 'time'
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('Family Start Time', html)
        self.assertIn('utcDate', html)
        # the JavaScript must contain plain numbers, not numpy repr's
        self.assertNotIn('np.float64', html)

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_output_format_and_zoom(self):
        """The 'html' output format and the zoom level should be accepted."""
        config.args.output = 'html'
        config.args.zoom = 7
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.test_dir.name)
        self.module.plot_families_map_with_folium(self.families)
        with open('family_map.html', encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('"zoom": 7', html)

    @unittest.skipUnless(FOLIUM_AVAILABLE, 'folium is not installed')
    def test_missing_coordinates_are_skipped(self):
        """Families without coordinates should be skipped, not plotted."""
        self.families[1].lon = None
        self.families[1].lat = None
        out_file = self._out_file()
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertIn('Family 1', html)
        self.assertNotIn('Family 2', html)


class TestCartopyBackend(_MapTestBase):
    """Test the cartopy map backend."""

    def setUp(self):
        """Set up a map without base map tiles."""
        self.families = _make_families()
        self.module = self.modules['map_families_cartopy']
        config.args = _map_args(backend='cartopy', mapstyle='no_basemap')
        self.addCleanup(plt.close, 'all')

    def test_marker_size_and_legend(self):
        """Markers should be scaled, with a legend explaining their size."""
        with patch.object(
            self.module, 'save_or_show_plot'
        ) as mocked_save:
            self.module.plot_families_map_with_cartopy(self.families)
        fig = mocked_save.call_args[0][0]
        ax = fig.axes[0]
        scatters = [
            collection for collection in ax.collections
            if getattr(collection, 'to_annotate', False)
        ]
        sizes = [scatter.get_sizes()[0] for scatter in scatters]
        self.assertEqual(sizes, [(2 * 5) ** 2, (2 * 14) ** 2])
        legend = ax.get_legend()
        self.assertEqual(legend.get_title().get_text(), 'Number of Events')
        self.assertEqual(
            [text.get_text() for text in legend.get_texts()],
            ['5', '12.5', '20']
        )

    def test_invalid_sizeby(self):
        """An invalid size quantity should produce an error and exit."""
        config.args.sizeby = 'invalid'
        _assert_rq_exit(
            self, self.module, self.module.plot_families_map_with_cartopy,
            self.families,
        )


if __name__ == '__main__':
    unittest.main()
