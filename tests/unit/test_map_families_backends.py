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
    def test_fixed_marker_radius(self):
        """All the family markers should have the same radius."""
        out_file = self._out_file()
        self.module.plot_families_map_with_folium(self.families)
        with open(out_file, encoding='utf8') as file_obj:
            html = file_obj.read()
        self.assertEqual(html.count('"radius": 5'), len(self.families))

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


if __name__ == '__main__':
    unittest.main()
