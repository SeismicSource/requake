# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for waveform-cache prefetch command.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import tempfile
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

from obspy import UTCDateTime

from requake.config import config
from requake.wfcache import commands as commands_module

MISSING = object()


def _build_event(evid):
    """Return minimal event object for prefetch tests."""
    return SimpleNamespace(
        evid=evid,
        orig_time=UTCDateTime('2020-01-01T00:00:00'),
        lat=10.0,
        lon=20.0,
        depth=5.0,
        mag=2.0,
        mag_type='Ml',
        trace_id=None,
    )


def _build_arrivals(*_args, **_kwargs):
    """Return deterministic P/S arrivals for prefetch tests."""
    p_arrival = SimpleNamespace(time=5.0)
    s_arrival = SimpleNamespace(time=10.0)
    return p_arrival, s_arrival, 0.0, 0.0


def _build_traceid_coords(*_args, **_kwargs):
    """Return deterministic station coordinates for known trace IDs."""
    return {
        'IV.ATFO..HHZ': {
            'latitude': 10.0,
            'longitude': 20.0,
        },
        'IV.RM33..HHN': {
            'latitude': 11.0,
            'longitude': 21.0,
        },
    }


def _build_group_trace():
    """Return a trace-like object compatible with local cut logic."""
    return SimpleNamespace(
        copy=lambda: SimpleNamespace(
            stats=SimpleNamespace(npts=10),
            trim=lambda **_kwargs: None,
        )
    )


class TestWaveformCachePrefetch(unittest.TestCase):
    """Validate waveform-cache prefetch command behavior."""

    def setUp(self):
        """Store and override config values used by prefetch command."""
        self.config_keys = (
            'args',
            'catalog_trace_id',
            'cc_pre_P',
            'cc_trace_length',
        )
        self.original_config = {
            key: config.get(key, MISSING) for key in self.config_keys
        }

    def tearDown(self):
        """Restore config values modified by tests."""
        for key, value in self.original_config.items():
            if value is MISSING:
                config.pop(key, None)
            else:
                config[key] = value

    def test_prefetch_honors_filters_and_max_events(self):
        """Prefetch should apply event filters and max-events bound."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_trace_id'] = ['IV.ATFO..HHZ']
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0
            config['args'] = Namespace(
                outdir=tmpdir,
                event_id=['ev1', 'ev3'],
                event_id_file=None,
                trace_id=['IV.ATFO..HHZ', 'IV.RM33..HHN'],
                max_events=1,
                batch_size=2,
                group_window='1h',
            )
            catalog = [_build_event('ev1'), _build_event('ev2')]
            with patch(
                'requake.catalog.read_stored_catalog',
                return_value=catalog,
            ), patch(
                'requake.catalog.fix_non_locatable_events',
            ), patch(
                'requake.waveforms.station_metadata.get_traceid_coords',
                side_effect=_build_traceid_coords,
            ), patch(
                'requake.waveforms.arrivals.get_arrivals',
                side_effect=_build_arrivals,
            ), patch(
                'requake.waveforms.get_waveform_from_client',
                return_value=_build_group_trace(),
            ) as mock_get_waveform, patch(
                'requake.wfcache.commands.read_waveform_from_cache',
                return_value=None,
            ), patch(
                'requake.wfcache.commands.should_skip_waveform_download',
                return_value=(False, ''),
            ), patch(
                'requake.wfcache.commands.write_waveform_to_cache',
                return_value=True,
            ), patch(
                'requake.wfcache.commands.clear_waveform_failure',
            ):
                with self.assertRaises(SystemExit) as exit_err:
                    commands_module.wfcache_prefetch()
            self.assertEqual(exit_err.exception.code, 0)
            self.assertEqual(mock_get_waveform.call_count, 2)

    def test_prefetch_uses_config_trace_ids_when_not_provided(self):
        """Prefetch should default to catalog_trace_id list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_trace_id'] = ['IV.ATFO..HHZ']
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0
            config['args'] = Namespace(
                outdir=tmpdir,
                event_id=[],
                event_id_file=None,
                trace_id=[],
                max_events=None,
                batch_size=10,
                group_window='1h',
            )
            catalog = [_build_event('ev1')]
            with patch(
                'requake.catalog.read_stored_catalog',
                return_value=catalog,
            ), patch(
                'requake.catalog.fix_non_locatable_events',
            ), patch(
                'requake.waveforms.station_metadata.get_traceid_coords',
                side_effect=_build_traceid_coords,
            ), patch(
                'requake.waveforms.arrivals.get_arrivals',
                side_effect=_build_arrivals,
            ), patch(
                'requake.waveforms.get_waveform_from_client',
                return_value=_build_group_trace(),
            ) as mock_get_waveform, patch(
                'requake.wfcache.commands.read_waveform_from_cache',
                return_value=None,
            ), patch(
                'requake.wfcache.commands.should_skip_waveform_download',
                return_value=(False, ''),
            ), patch(
                'requake.wfcache.commands.write_waveform_to_cache',
                return_value=True,
            ), patch(
                'requake.wfcache.commands.clear_waveform_failure',
            ):
                with self.assertRaises(SystemExit) as exit_err:
                    commands_module.wfcache_prefetch()
            self.assertEqual(exit_err.exception.code, 0)
            self.assertEqual(mock_get_waveform.call_count, 1)

    def test_prefetch_groups_requests_within_window(self):
        """Prefetch should download one grouped window per trace when close."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_trace_id'] = ['IV.ATFO..HHZ']
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0
            config['args'] = Namespace(
                outdir=tmpdir,
                event_id=[],
                event_id_file=None,
                trace_id=['IV.ATFO..HHZ'],
                max_events=None,
                batch_size=10,
                group_window='1h',
            )
            ev1 = _build_event('ev1')
            ev2 = _build_event('ev2')
            ev2.orig_time = ev1.orig_time + 60
            catalog = [ev1, ev2]
            with patch(
                'requake.catalog.read_stored_catalog',
                return_value=catalog,
            ), patch(
                'requake.catalog.fix_non_locatable_events',
            ), patch(
                'requake.waveforms.station_metadata.get_traceid_coords',
                side_effect=_build_traceid_coords,
            ), patch(
                'requake.waveforms.arrivals.get_arrivals',
                side_effect=_build_arrivals,
            ), patch(
                'requake.waveforms.get_waveform_from_client',
                return_value=_build_group_trace(),
            ) as mock_get_waveform, patch(
                'requake.wfcache.commands.read_waveform_from_cache',
                return_value=None,
            ), patch(
                'requake.wfcache.commands.should_skip_waveform_download',
                return_value=(False, ''),
            ), patch(
                'requake.wfcache.commands.write_waveform_to_cache',
                return_value=True,
            ), patch(
                'requake.wfcache.commands.clear_waveform_failure',
            ):
                with self.assertRaises(SystemExit) as exit_err:
                    commands_module.wfcache_prefetch()
            self.assertEqual(exit_err.exception.code, 0)
            self.assertEqual(mock_get_waveform.call_count, 1)

    def test_prefetch_resolves_coords_once_per_event(self):
        """Prefetch should resolve metadata once for the full run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config['catalog_trace_id'] = ['IV.ATFO..HHZ']
            config['cc_pre_P'] = 1.0
            config['cc_trace_length'] = 4.0
            config['args'] = Namespace(
                outdir=tmpdir,
                event_id=[],
                event_id_file=None,
                trace_id=['IV.ATFO..HHZ', 'IV.RM33..HHN'],
                max_events=None,
                batch_size=10,
                group_window='1h',
            )
            catalog = [_build_event('ev1'), _build_event('ev2')]
            with patch(
                'requake.catalog.read_stored_catalog',
                return_value=catalog,
            ), patch(
                'requake.catalog.fix_non_locatable_events',
            ), patch(
                'requake.waveforms.station_metadata.get_traceid_coords',
                side_effect=_build_traceid_coords,
            ) as mock_coords, patch(
                'requake.waveforms.arrivals.get_arrivals',
                side_effect=_build_arrivals,
            ), patch(
                'requake.waveforms.get_waveform_from_client',
                return_value=_build_group_trace(),
            ), patch(
                'requake.wfcache.commands.read_waveform_from_cache',
                return_value=None,
            ), patch(
                'requake.wfcache.commands.should_skip_waveform_download',
                return_value=(False, ''),
            ), patch(
                'requake.wfcache.commands.write_waveform_to_cache',
                return_value=True,
            ), patch(
                'requake.wfcache.commands.clear_waveform_failure',
            ):
                with self.assertRaises(SystemExit) as exit_err:
                    commands_module.wfcache_prefetch()
            self.assertEqual(exit_err.exception.code, 0)
            self.assertEqual(mock_coords.call_count, 1)


if __name__ == '__main__':
    unittest.main()
