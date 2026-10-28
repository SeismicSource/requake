# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the run parameter snapshots.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import json
import unittest
import tempfile
import os
from argparse import Namespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.config import config
from requake.config.run_params import (
    catalog_parameters,
    family_build_parameters,
    format_parameters,
    parameters_digest,
    parameters_json,
    scan_parameters,
)


class TestRunParams(unittest.TestCase):
    """Test the parameter snapshots and their digest."""

    def setUp(self):
        """Create a temporary directory for the catalog file path."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _config(self, **args_overrides):
        """Return a config patch with representative parameters."""
        args = Namespace(
            outdir=self.test_dir.name,
            catalog_file=None,
            traceid=None,
            freq_band=None,
        )
        for key, value in args_overrides.items():
            setattr(args, key, value)
        return patch.dict(
            config,
            {
                'args': args,
                'outdir': self.test_dir.name,
                'catalog_start_times': [UTCDateTime('2020-01-01')],
                'catalog_end_times': [UTCDateTime('2020-02-01')],
                'catalog_fdsn_event_urls': ['http://example.com'],
                'catalog_lat_min': 12.5,
                'catalog_lat_max': 18.5,
                'catalog_lon_min': -62.5,
                'catalog_lon_max': -58.5,
                'catalog_depth_min': 0.0,
                'catalog_depth_max': 60.0,
                'catalog_mag_min': 2.0,
                'catalog_mag_max': 4.0,
                'catalog_search_range': 30.0,
                'catalog_trace_id': ['XX.TEST.00.BHZ'],
                'fdsn_station_url': 'http://station.example.com',
                'station_metadata_path': None,
                'fdsn_dataselect_url': 'http://data.example.com',
                'sds_data_path': None,
                'event_data_path': None,
                'cc_pre_P': 5.0,
                'cc_trace_length': 120.0,
                'cc_freq_min': 2.0,
                'cc_freq_max': 10.0,
                'cc_max_shift': 5.0,
                'cc_allow_negative': False,
                'clustering_algorithm': 'shared',
                'cc_min': 0.95,
                'sort_families_by': 'time',
                'distance_from_lon': None,
                'distance_from_lat': None,
            },
            clear=False,
        )

    def test_catalog_parameters_file_source(self):
        """A file source is recorded with its absolute path."""
        catalog_file = os.path.join(self.test_dir.name, 'catalog.csv')
        with self._config(catalog_file=catalog_file):
            params = catalog_parameters()
        self.assertEqual(params['catalog_source']['type'], 'file')
        self.assertEqual(params['catalog_source']['path'], catalog_file)
        self.assertEqual(params['mag_min'], 2.0)

    def test_catalog_parameters_fdsn_source(self):
        """An FDSN source records the event URLs."""
        with self._config():
            params = catalog_parameters()
        self.assertEqual(params['catalog_source']['type'], 'fdsn')
        self.assertEqual(
            params['catalog_source']['urls'], ['http://example.com']
        )

    def test_scan_parameters_traceid_override(self):
        """A command-line traceid overrides the configured trace ids."""
        with self._config(traceid='YY.OTHR.00.HHZ'):
            params = scan_parameters()
        self.assertEqual(params['catalog_trace_id'], ['YY.OTHR.00.HHZ'])

    def test_scan_parameters_freq_band_override(self):
        """A command-line frequency band overrides the configured one."""
        with self._config(freq_band=('1', '4')):
            params = scan_parameters()
        self.assertEqual(params['cc_freq_min'], 1.0)
        self.assertEqual(params['cc_freq_max'], 4.0)

    def test_family_build_parameters(self):
        """The clustering method and parameters are recorded."""
        with self._config():
            params = family_build_parameters()
        self.assertEqual(params['clustering_algorithm'], 'shared')
        self.assertEqual(params['cc_min'], 0.95)

    def test_digest_is_stable_and_sensitive(self):
        """The digest is deterministic and changes with the parameters."""
        with self._config():
            first = parameters_digest(family_build_parameters())
            second = parameters_digest(family_build_parameters())
        self.assertEqual(first, second)
        with patch.dict(config, {'cc_min': 0.9}, clear=False):
            third = parameters_digest(family_build_parameters())
        self.assertNotEqual(first, third)

    def test_parameters_json_is_canonical(self):
        """The JSON snapshot sorts keys and serializes non-JSON values."""
        payload = parameters_json(
            {'b': 1, 'a': UTCDateTime('2020-01-01T00:00:00')}
        )
        self.assertTrue(payload.startswith('{"a"'))
        self.assertIn('2020-01-01', payload)
        self.assertEqual(json.loads(payload)['b'], 1)

    def test_format_parameters_flattens_sequences(self):
        """Stored parameters are rendered as sorted key/value pairs."""
        rows = format_parameters(
            json.dumps(
                {'ids': ['a', 'b'], 'nested': {'k': 1}, 'value': 2}
            )
        )
        self.assertEqual([key for key, _ in rows], ['ids', 'nested', 'value'])
        self.assertEqual(rows[0][1], 'a, b')
        self.assertIn('"k": 1', rows[1][1])

    def test_format_parameters_handles_invalid_json(self):
        """Malformed JSON is returned as a single row."""
        rows = format_parameters('not-json')
        self.assertEqual(rows, [('params_json', 'not-json')])


if __name__ == '__main__':
    unittest.main()
