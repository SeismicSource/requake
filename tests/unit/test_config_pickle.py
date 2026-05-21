# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for configuration object pickling.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import multiprocessing as mp
import pickle
import unittest
from argparse import Namespace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from requake.config import (
    from_picklable_config_dict,
    to_picklable_config_dict,
)
from requake.config.config import Config
from requake.config.utils import (
    parse_configspec,
    read_config,
    validate_config,
)


def _worker_read_snapshot(cfg_dict):
    """Worker-side function for multiprocessing smoke tests."""
    cfg = from_picklable_config_dict(cfg_dict)
    return cfg.args.action, cfg.cc_min


class TestConfigPickle(unittest.TestCase):
    """Validate that Config instances loaded from files are pickleable."""

    def _build_runtime_config(self, config_file):
        """Build a Config object by reading and validating a config file."""
        configspec = parse_configspec()
        config_obj = read_config(str(config_file), configspec)

        # Keep behavior aligned with requake.config.rq_setup.configure().
        for key, value in config_obj.dict().items():
            if value == 'None':
                config_obj[key] = None

        validate_config(config_obj)

        cfg = Config()
        cfg.update(config_obj)

        outdir = Path(config_file).parent / 'unit_test_out'
        args = Namespace(
            action='print_catalog',
            configfile=str(config_file),
            outdir=str(outdir),
        )
        cfg.args = args
        cfg.scan_catalog_pairs_file = str(outdir / 'requake.event_pairs.csv')
        cfg.build_families_outfile = str(outdir / 'requake.event_families.csv')
        cfg.template_dir = str(outdir / 'templates')
        cfg.inventory = None
        return cfg

    def _get_reference_config_file(self):
        """Return the integration config used by pickle tests."""
        return Path(__file__).resolve().parents[2].joinpath(
            'tests', 'integration', 'test_fdsnws', 'requake.conf'
        )

    def test_config_loaded_from_file_is_pickleable(self):
        """A Config from a real config file survives pickle round-trip."""
        config_file = self._get_reference_config_file()

        cfg = self._build_runtime_config(config_file)
        blob = pickle.dumps(cfg)
        loaded = pickle.loads(blob)

        self.assertIsInstance(loaded, Config)
        self.assertEqual(
            loaded.catalog_fdsn_event_url,
            cfg.catalog_fdsn_event_url,
        )
        self.assertEqual(
            loaded['catalog_fdsn_event_url'],
            cfg['catalog_fdsn_event_url'],
        )
        self.assertEqual(loaded.args.action, 'print_catalog')
        self.assertEqual(loaded.args.configfile, str(config_file))
        self.assertIsNone(loaded.inventory)

    def test_picklable_snapshot_strips_runtime_clients(self):
        """Snapshot helper must drop runtime clients and stay pickleable."""
        config_file = self._get_reference_config_file()

        cfg = self._build_runtime_config(config_file)
        cfg.station_client = lambda: None
        cfg.dataselect_client = lambda: None
        cfg.catalog_fdsn_event_clients = [lambda: None]

        with self.assertRaises(Exception):
            pickle.dumps(cfg)

        snapshot = to_picklable_config_dict(cfg)
        blob = pickle.dumps(snapshot)
        loaded = pickle.loads(blob)

        self.assertNotIn('station_client', loaded)
        self.assertNotIn('dataselect_client', loaded)
        self.assertNotIn('catalog_fdsn_event_clients', loaded)
        self.assertIsInstance(loaded['args'], dict)
        self.assertEqual(loaded['args']['action'], 'print_catalog')

    def test_picklable_snapshot_can_drop_inventory(self):
        """Inventory can be excluded explicitly when workers do not need it."""
        config_file = self._get_reference_config_file()

        cfg = self._build_runtime_config(config_file)
        cfg.inventory = {'k': 'v'}

        snapshot = to_picklable_config_dict(cfg, drop_inventory=True)
        self.assertNotIn('inventory', snapshot)

    def test_config_can_be_rebuilt_from_snapshot(self):
        """Snapshot can be rebuilt to Config with args as Namespace."""
        config_file = self._get_reference_config_file()

        cfg = self._build_runtime_config(config_file)
        snapshot = to_picklable_config_dict(cfg)
        rebuilt = from_picklable_config_dict(snapshot)

        self.assertIsInstance(rebuilt, Config)
        self.assertIsInstance(rebuilt.args, Namespace)
        self.assertEqual(rebuilt.args.action, cfg.args.action)
        self.assertEqual(
            rebuilt.catalog_fdsn_event_url,
            cfg.catalog_fdsn_event_url,
        )

    def test_process_pool_can_consume_picklable_snapshot(self):
        """Snapshot can be sent to a spawned process and reconstructed."""
        config_file = self._get_reference_config_file()

        cfg = self._build_runtime_config(config_file)
        cfg.station_client = lambda: None
        snapshot = to_picklable_config_dict(cfg)

        mp_context = mp.get_context('spawn')
        with ProcessPoolExecutor(max_workers=1, mp_context=mp_context) as pool:
            future = pool.submit(_worker_read_snapshot, snapshot)
            action, cc_min = future.result(timeout=15)

        self.assertEqual(action, 'print_catalog')
        self.assertEqual(cc_min, cfg.cc_min)


if __name__ == '__main__':
    unittest.main()
