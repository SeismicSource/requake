# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for catalog round-trip (write/read) consistency."""

import unittest
import tempfile
import os
from obspy import UTCDateTime
from requake.catalog import RequakeEvent, RequakeCatalog


class TestCatalogRoundtrip(unittest.TestCase):
    """Test catalog round-trip write/read consistency."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _create_synthetic_events(self, n=5):
        """
        Create n synthetic RequakeEvent objects with deterministic values.

        :param n: number of events to create
        :type n: int
        :return: list of RequakeEvent objects
        :rtype: list
        """
        events = []
        for i in range(n):
            ev = RequakeEvent(
                evid=f'event_{i:03d}',
                orig_time=UTCDateTime(2020, 1, 1, 0, 0, i),
                lon=10.0 + i * 0.1,
                lat=45.0 + i * 0.1,
                depth=10.0 + i,
                mag_type='Mw',
                mag=4.0 + i * 0.1,
                author='TEST',
                catalog='TEST_CATALOG',
                contributor='test_contributor',
                contributor_id='test_id',
                mag_author='test_author',
                location_name='Test Location'
            )
            events.append(ev)
        return events

    def _assert_events_equal(self, ev_in, ev_out):
        """Assert equality for two events with numeric tolerances."""
        self.assertEqual(ev_in.evid, ev_out.evid)
        self.assertAlmostEqual(
            ev_in.orig_time.timestamp,
            ev_out.orig_time.timestamp,
            places=3
        )
        self.assertAlmostEqual(ev_in.lon, ev_out.lon, places=6)
        self.assertAlmostEqual(ev_in.lat, ev_out.lat, places=6)
        self.assertAlmostEqual(ev_in.depth, ev_out.depth, places=6)
        self.assertAlmostEqual(ev_in.mag, ev_out.mag, places=6)
        self.assertEqual(ev_in.mag_type, ev_out.mag_type)
        self.assertEqual(ev_in.author, ev_out.author)
        self.assertEqual(ev_in.catalog, ev_out.catalog)
        self.assertEqual(ev_in.contributor, ev_out.contributor)
        self.assertEqual(ev_in.contributor_id, ev_out.contributor_id)
        self.assertEqual(ev_in.mag_author, ev_out.mag_author)
        self.assertEqual(ev_in.location_name, ev_out.location_name)

    def test_catalog_write_read_roundtrip(self):
        """
        Test that writing and reading a catalog preserves event data.

        Write N synthetic events with RequakeCatalog.write(), read back
        with RequakeCatalog.read(), and assert field-by-field equality.
        """
        # Create synthetic events
        n_events = 5
        events = self._create_synthetic_events(n_events)

        # Write catalog
        catalog_path = os.path.join(self.test_dir.name, 'test_catalog.txt')
        cat_out = RequakeCatalog()
        cat_out.extend(events)
        cat_out.write(catalog_path)

        # Read catalog
        cat_in = RequakeCatalog()
        cat_in.read(catalog_path)

        # Assert number of events
        self.assertEqual(
            len(cat_in), n_events,
            'Catalog size mismatch after round-trip'
        )

        # Build a map of events by evid for comparison
        # (order may differ due to deduplication and sorting)
        ev_map_in = {ev.evid: ev for ev in cat_in}
        ev_map_out = {ev.evid: ev for ev in cat_out}

        # Assert all evids are present
        self.assertEqual(
            set(ev_map_in.keys()), set(ev_map_out.keys()),
            'Event IDs do not match after round-trip'
        )

        self._assert_events_equal(
            ev_map_in['event_000'], ev_map_out['event_000'])
        self._assert_events_equal(
            ev_map_in['event_001'], ev_map_out['event_001'])
        self._assert_events_equal(
            ev_map_in['event_002'], ev_map_out['event_002'])
        self._assert_events_equal(
            ev_map_in['event_003'], ev_map_out['event_003'])
        self._assert_events_equal(
            ev_map_in['event_004'], ev_map_out['event_004'])

    def test_catalog_preserves_all_fdsn_columns(self):
        """
        Verify that all 13 FDSN schema columns are present after a round-trip.

        The FDSN text format includes: evid, orig_time, lat, lon, depth,
        author, catalog, contributor, contributor_id, mag_type, mag,
        mag_author, location_name.
        """
        # Create synthetic event
        events = self._create_synthetic_events(1)

        # Write and read
        catalog_path = os.path.join(self.test_dir.name, 'test_fdsn.txt')
        cat_out = RequakeCatalog()
        cat_out.extend(events)
        cat_out.write(catalog_path)

        cat_in = RequakeCatalog()
        cat_in.read(catalog_path)

        # Check that all fields are present (not None)
        ev = cat_in[0]
        self.assertIsNotNone(ev.evid, 'evid is None')
        self.assertIsNotNone(ev.orig_time, 'orig_time is None')
        self.assertIsNotNone(ev.lat, 'lat is None')
        self.assertIsNotNone(ev.lon, 'lon is None')
        self.assertIsNotNone(ev.depth, 'depth is None')
        self.assertIsNotNone(ev.author, 'author is None')
        self.assertIsNotNone(ev.catalog, 'catalog is None')
        self.assertIsNotNone(ev.contributor, 'contributor is None')
        self.assertIsNotNone(ev.contributor_id, 'contributor_id is None')
        self.assertIsNotNone(ev.mag_type, 'mag_type is None')
        self.assertIsNotNone(ev.mag, 'mag is None')
        self.assertIsNotNone(ev.mag_author, 'mag_author is None')
        self.assertIsNotNone(ev.location_name, 'location_name is None')

    def test_catalog_empty_write_read(self):
        """Test that empty catalog round-trip produces empty catalog."""
        # Write empty catalog
        catalog_path = os.path.join(self.test_dir.name, 'test_empty.txt')
        cat_out = RequakeCatalog()
        cat_out.write(catalog_path)

        # Read empty catalog
        cat_in = RequakeCatalog()
        cat_in.read(catalog_path)

        # Assert empty
        self.assertEqual(len(cat_in), 0, 'Empty catalog should remain empty')


if __name__ == '__main__':
    unittest.main()
