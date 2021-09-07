#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Flag a family of repeating earthquakes as valid or not valid.

:copyright:
    2021 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
logger = logging.getLogger(__name__.split('.')[-1])
import csv
import shutil
from tempfile import NamedTemporaryFile


def flag_family(config):
    family_number = config.args.family_number
    true_words = ['True', 'true', 'True', 't', 'T']
    false_words = ['False', 'false', 'FALSE', 'f', 'F']
    is_valid = config.args.is_valid
    if is_valid not in true_words + false_words:
        logger.error(
            'Invalid choice for "is_valid": "{}". '
            'Enter either "true" ("t") or "false" ("f")'.format(is_valid))
    is_valid = is_valid in true_words
    tmpfile = NamedTemporaryFile(mode='w', delete=False)
    with open(config.build_families_outfile, 'r') as csvfile, tmpfile:
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
    logger.info('Family "{}" flagged as {}'.format(
        family_number, text[is_valid]))
