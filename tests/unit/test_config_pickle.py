# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for configuration object pickling."""

import pickle
import unittest
from argparse import Namespace
from pathlib import Path

from requake.config.config import Config
from requake.config.utils import (
    parse_configspec,
    read_config,
    validate_config,
)


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
        cfg.scan_catalog_file = str(outdir / 'requake.catalog.txt')
        cfg.scan_catalog_pairs_file = str(outdir / 'requake.event_pairs.csv')
        cfg.build_families_outfile = str(outdir / 'requake.event_families.csv')
        cfg.template_dir = str(outdir / 'templates')
        cfg.inventory = None
        return cfg

    def test_config_loaded_from_file_is_pickleable(self):
        """A Config from a real config file survives pickle round-trip."""
        repo_root = Path(__file__).resolve().parents[2]
        config_file = (
            repo_root / 'tests' / 'integration' /
            'test_fdsnws' / 'requake.conf'
        )

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


if __name__ == '__main__':
    unittest.main()
