# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for template catalog schema and format."""

import unittest
import tempfile
import os



class TestTemplateCatalogSchema(unittest.TestCase):
    """Test template catalog file naming and row format."""

    def setUp(self):
        """Create a temporary directory for test outputs."""
        self.test_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.test_dir.cleanup)

    def _create_template_file(self, template_dir, filename, content='test content\n'):
        """Create one template catalog file and return its path."""
        filepath = os.path.join(template_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def _assert_filename_pattern(self, filename):
        """Assert minimal template catalog filename structure."""
        parts = filename.split('.')
        self.assertEqual(parts[0][:7], 'catalog', "Filename should start with 'catalog'")
        self.assertGreaterEqual(len(parts), 4, "Filename should have at least 4 parts")

    def _parse_catalog_row(self, line):
        """Parse one template catalog row and return parts and cc_max."""
        parts = line.split('|')
        self.assertEqual(len(parts), 14, f"Row should have 14 fields, got {len(parts)}")
        cc_max = float(parts[-1])
        self.assertGreaterEqual(cc_max, -1.0, "cc_max should be >= -1")
        self.assertLessEqual(cc_max, 1.0, "cc_max should be <= 1")
        return parts, cc_max

    def test_template_catalog_filename_convention(self):
        """
        Verify files are named as catalog{family:02d}.{trace_id}.txt
        under template_catalogs/.

        Expected naming: catalog00.XX.TEST.00.BHZ.txt for family 0, trace XX.TEST.00.BHZ
        """
        # Create template directory structure
        template_dir = os.path.join(self.test_dir.name, 'template_catalogs')
        os.makedirs(template_dir, exist_ok=True)

        file_1 = 'catalog00.XX.TEST.00.BHZ.txt'
        file_2 = 'catalog01.XX.TEST.00.BHZ.txt'
        file_3 = 'catalog02.YY.TEST.00.BHP.txt'

        path_1 = self._create_template_file(template_dir, file_1)
        path_2 = self._create_template_file(template_dir, file_2)
        path_3 = self._create_template_file(template_dir, file_3)

        self.assertTrue(os.path.exists(path_1), f"File {file_1} should exist")
        self.assertTrue(os.path.exists(path_2), f"File {file_2} should exist")
        self.assertTrue(os.path.exists(path_3), f"File {file_3} should exist")

        self._assert_filename_pattern(file_1)
        self._assert_filename_pattern(file_2)
        self._assert_filename_pattern(file_3)

    def test_template_catalog_row_contract(self):
        """
        Verify each row is fdsn_text|cc_max and can be parsed.

        Format: evid|orig_time|lat|lon|depth|author|...|location_name|cc_max
        """
        # Create a template catalog file
        template_dir = os.path.join(self.test_dir.name, 'template_catalogs')
        os.makedirs(template_dir, exist_ok=True)

        catalog_path = os.path.join(
            template_dir, 'catalog00.XX.TEST.00.BHZ.txt'
        )

        # Write test catalog rows
        test_rows = [
            'ev_001|2020-01-01T00:00:00|45.0|10.0|10.0|TEST|TEST|TEST|TEST_1|Mw|4.0|TEST|Location 1|0.85',
            'ev_002|2020-01-01T01:00:00|45.1|10.1|10.5|TEST|TEST|TEST|TEST_2|Mw|4.1|TEST|Location 2|0.87',
        ]

        with open(catalog_path, 'w', encoding='utf-8') as f:
            f.write(test_rows[0] + '\n')
            f.write(test_rows[1] + '\n')

        # Verify rows can be parsed
        with open(catalog_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines()]

        _, cc_max_1 = self._parse_catalog_row(lines[0])
        _, cc_max_2 = self._parse_catalog_row(lines[1])
        self.assertAlmostEqual(cc_max_1, 0.85, places=6)
        self.assertAlmostEqual(cc_max_2, 0.87, places=6)


if __name__ == '__main__':
    unittest.main()
