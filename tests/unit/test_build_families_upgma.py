# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the UPGMA family build.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import unittest
import tempfile
from argparse import Namespace
from unittest.mock import patch
from scipy.spatial.distance import squareform
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.database.catalog import write_catalog
from requake.database.catalogs import create_catalog
from requake.database.families import read_families
from requake.database.pairs import PairRecord, write_pair_records
from requake.database.scans import create_scan
from requake.families import build_families
from requake.families.build_families import (
    _build_families_from_upgma,
    _condensed_distances,
)

TRACE_ID = 'XX.TEST.00.BHZ'
ORIG_TIME = UTCDateTime('2020-01-01T00:00:00')


def _event(evid, offset_seconds):
    """Return a synthetic event."""
    return RequakeEvent(
        evid=evid,
        orig_time=ORIG_TIME + offset_seconds,
        lon=10.0,
        lat=45.0,
        depth=10.0,
        mag_type='Mw',
        mag=3.0,
        trace_id=TRACE_ID,
    )


def _events(evids):
    """Return a dictionary of synthetic events."""
    return {
        evid: _event(evid, idx * 3600)
        for idx, evid in enumerate(sorted(evids))
    }


def _link(events, evid1, evid2, cc):
    """Store a correlation in both events."""
    events[evid1].correlations[evid2] = cc
    events[evid2].correlations[evid1] = cc


def _family_evids(families):
    """Return the family event ids as a sorted list of sorted lists."""
    return sorted(sorted(event.evid for event in family)
                  for family in families)


class TestUpgmaDistances(unittest.TestCase):
    """Test the condensed distance matrix."""

    def test_layout_matches_scipy(self):
        """Distances must follow the layout used by scipy."""
        events = _events(['a', 'b', 'c', 'd'])
        _link(events, 'a', 'b', 0.9)
        _link(events, 'a', 'c', 0.8)
        _link(events, 'c', 'd', 0.7)
        evids, distances = _condensed_distances(events)
        square = squareform(distances)
        idx = {evid: i for i, evid in enumerate(evids)}
        self.assertAlmostEqual(square[idx['a'], idx['b']], 0.1)
        self.assertAlmostEqual(square[idx['a'], idx['c']], 0.2)
        self.assertAlmostEqual(square[idx['c'], idx['d']], 0.3)

    def test_unlinked_pairs_get_max_distance(self):
        """Pairs without a correlation must be maximally distant."""
        events = _events(['a', 'b', 'c'])
        _link(events, 'a', 'b', 0.99)
        evids, distances = _condensed_distances(events)
        square = squareform(distances)
        idx = {evid: i for i, evid in enumerate(evids)}
        self.assertAlmostEqual(square[idx['a'], idx['b']], 0.01)
        self.assertEqual(square[idx['a'], idx['c']], 1.0)
        self.assertEqual(square[idx['b'], idx['c']], 1.0)


class TestUpgmaClustering(unittest.TestCase):
    """Test the clustering on an events dictionary."""

    def setUp(self):
        """Provide the config key used when appending to a family."""
        patcher = patch.dict(
            config, {'mag_to_slip_model': 'NJ1998'}, clear=False
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_less_than_two_events_gives_no_family(self):
        """A single event cannot form a family."""
        events = _events(['a'])
        families = _build_families_from_upgma(events, cc_min=0.95)
        self.assertEqual(families, [])

    def test_chain_is_not_merged_through_unlinked_pair(self):
        """Events a and c are not joined when their pair is missing."""
        events = _events(['a', 'b', 'c'])
        _link(events, 'a', 'b', 0.99)
        _link(events, 'b', 'c', 0.99)
        families = _build_families_from_upgma(events, cc_min=0.95)
        self.assertEqual(_family_evids(families), [['a', 'b']])

    def test_disjoint_families_stay_separate(self):
        """Two unconnected pairs must give two families."""
        events = _events(['a', 'b', 'c', 'd'])
        _link(events, 'a', 'b', 0.99)
        _link(events, 'c', 'd', 0.98)
        families = _build_families_from_upgma(events, cc_min=0.95)
        self.assertEqual(_family_evids(families), [['a', 'b'], ['c', 'd']])


class TestUpgmaBuildFromDb(unittest.TestCase):
    """Test that the build only reads pairs above cc_min."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _patch_config(self):
        """Patch the global config for the temporary database."""
        return patch.dict(
            config,
            {
                'args': Namespace(outdir=self.test_dir.name),
                'outdir': self.test_dir.name,
                'clustering_algorithm': 'UPGMA',
                'cc_min': 0.95,
                'sort_families_by': 'time',
                'distance_from_lon': None,
                'distance_from_lat': None,
                'mag_to_slip_model': 'NJ1998',
            },
            clear=False,
        )

    def _seed_db(self, events):
        """Write catalog, scan and event pairs into the database."""
        catalog_id = create_catalog(
            'test-catalog-hash', '{}', source='test',
            nevents=len(events)
        )
        write_catalog(list(events.values()), catalog_id)
        scan_id = create_scan(
            catalog_id, 'test-scan-hash', '{}', nevents=len(events)
        )
        write_pair_records(
            [
                PairRecord(
                    events['ev_a'], events['ev_b'], TRACE_ID,
                    100, 0.99, sampling_rate_hz=40.0,
                ),
                PairRecord(
                    events['ev_b'], events['ev_c'], TRACE_ID,
                    100, 0.99, sampling_rate_hz=40.0,
                ),
                # below cc_min: must not link ev_a and ev_c
                PairRecord(
                    events['ev_a'], events['ev_c'], TRACE_ID,
                    100, 0.40, sampling_rate_hz=40.0,
                ),
                # below cc_min: ev_d must not be read at all
                PairRecord(
                    events['ev_c'], events['ev_d'], TRACE_ID,
                    100, 0.30, sampling_rate_hz=40.0,
                ),
            ],
            scan_id,
            append=False,
        )

    def test_pairs_below_cc_min_are_ignored(self):
        """Weak pairs must not be read, nor join events into a family."""
        events = _events(['ev_a', 'ev_b', 'ev_c', 'ev_d'])
        with self._patch_config():
            self._seed_db(events)
            build_families()
            stored_families = read_families()
        self.assertEqual(_family_evids(stored_families), [['ev_a', 'ev_b']])
