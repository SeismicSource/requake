# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Unit tests for the per-event family listing.

:copyright:
    2021-2026 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""

import importlib
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch
from obspy import UTCDateTime
from requake.catalog import RequakeEvent
from requake.config import config
from requake.families.families import Family


# The ``config`` and ``read_selected_families`` names are imported by
# value in the module, so patch them there instead of on the source
# modules.
print_families_module = importlib.import_module(
    'requake.families.print_families'
)


def _make_family(number, events):
    """Build a family from a list of (evid, orig_time, mag) tuples."""
    family = Family(number)
    with patch.dict(config, {'mag_to_slip_model': 'NJ1998'}, clear=False):
        for evid, orig_time, mag in events:
            family.append(RequakeEvent(
                evid=evid,
                trace_id='XX.TEST.00.BHZ',
                orig_time=UTCDateTime(orig_time),
                lon=11.0,
                lat=46.0,
                depth=6.0,
                mag_type='MLv',
                mag=mag,
            ))
    return family


class TestPrintFamilyEvents(unittest.TestCase):
    """Test the per-event listing of ``print_families --events``."""

    def _run(self, families):
        """Run print_families() in events mode, capturing the table."""
        table = {}
        config_stub = SimpleNamespace(
            args=Namespace(format='simple', events=True)
        )

        def fake_display(headers_fmt, rows=None, **kwargs):
            table['headers_fmt'] = headers_fmt
            table['rows'] = rows
            table['kwargs'] = kwargs

        with patch.multiple(
            print_families_module,
            config=config_stub,
            read_selected_families=lambda: families,
            _display_table=fake_display,
        ):
            print_families_module.print_families()
        return table

    @staticmethod
    def _families():
        """Return two families, in reverse chronological order."""
        return [
            _make_family(1, [
                ('ev_b', '2020-01-02T00:00:00', 3.0),
                ('ev_a', '2020-01-01T00:00:00', 2.0),
            ]),
            _make_family(2, [
                ('ev_c', '2020-01-05T00:00:00', 4.0),
            ]),
        ]

    def test_headers(self):
        """The table must show the event columns, after the family."""
        table = self._run(self._families())
        headers = [h[0] for h in table['headers_fmt']]
        self.assertEqual(headers, [
            'family', 'evid', 'origin time', 'longitude', 'latitude',
            'depth\n(km)', 'mag\ntype', 'mag'
        ])

    def test_one_row_per_event(self):
        """Each event must produce one row, ordered by family then time."""
        table = self._run(self._families())
        rows = table['rows']
        self.assertEqual(len(rows), 3)
        self.assertEqual([row[0] for row in rows], [1, 1, 2])
        self.assertEqual([row[1] for row in rows], ['ev_a', 'ev_b', 'ev_c'])

    def test_row_content(self):
        """Rows must carry the event origin, depth, magnitude type, mag."""
        table = self._run(self._families())
        first_row = table['rows'][0]
        self.assertEqual(first_row[1], 'ev_a')
        self.assertEqual(first_row[2], UTCDateTime('2020-01-01T00:00:00'))
        self.assertEqual(first_row[3], 11.0)
        self.assertEqual(first_row[4], 46.0)
        self.assertEqual(first_row[5], 6.0)
        self.assertEqual(first_row[6], 'MLv')
        self.assertEqual(first_row[7], 2.0)

    def test_copy_copies_the_event_id(self):
        """Copying a row must copy the event ID, not the family number."""
        table = self._run(self._families())
        copy_fn = table['kwargs']['copy_fn']
        self.assertEqual(table['kwargs']['copy_label'], 'evid')
        self.assertEqual(copy_fn(['1', 'ev_a']), 'ev_a')


if __name__ == '__main__':
    unittest.main()
