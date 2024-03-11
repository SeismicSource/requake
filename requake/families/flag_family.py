# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Flag a family of repeating earthquakes as valid or not valid.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
import shutil
from tempfile import NamedTemporaryFile
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def flag_family(config):
    """
    Flag a family of repeating earthquakes as valid or not valid.

    :param config: Configuration object.
    :type config: config.Config
    """
    family_number = config.args.family_number
    true_words = ['True', 'true', 'True', 't', 'T']
    false_words = ['False', 'false', 'FALSE', 'f', 'F']
    is_valid = config.args.is_valid
    if is_valid not in true_words + false_words:
        logger.error(
            f'Invalid choice for "is_valid": "{is_valid}". '
            'Enter either "true" ("t") or "false" ("f")'
        )
    is_valid = is_valid in true_words
    with open(config.build_families_outfile, 'r', encoding='utf-8') as csvfile:
        with NamedTemporaryFile(mode='w', delete=False) as tmpfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames
            writer = csv.DictWriter(tmpfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                if row['family_number'] == family_number:
                    row['valid'] = is_valid
                writer.writerow(row)
    shutil.move(tmpfile.name, config.build_families_outfile)
    text = {True: 'valid', False: 'not valid'}
    logger.info(f'Family "{family_number}" flagged as {text[is_valid]}')
