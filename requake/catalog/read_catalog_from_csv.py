# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Read an event catalog from a CSV file.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
from obspy import UTCDateTime
from ..formulas.conversion import float_or_none, int_or_none
from ..catalog.catalog import (
    RequakeCatalog, RequakeEvent, generate_evid)
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _field_match_score(field, field_list):
    """
    Return the length of the longest substring of field that matches any of
    the field names in field_list.

    :param field: field name
    :type field: str
    :param field_list: list of field names
    :type field_list: list of str

    :return: the length of the longest substring of field that matches any of
        the field names in field_list
    :rtype: int
    """
    scores = [
        len(guess)
        for guess in field_list
        if guess in field.lower()
    ]
    try:
        return max(scores)
    except ValueError:
        return 0


def _guess_field_names(input_fields):
    """
    Guess the field names corresponding to origin time, latitude, longitude,
    depth, magnitude and magnitude type.

    :param input_fields: list of field names
    :type input_fields: list of str

    :return: a dictionary with field names for origin time, latitude,
        longitude, depth, magnitude and magnitude type
    :rtype: dict
    """
    field_guesses = {
        'evid': ['evid', 'event_id', 'eventid', 'event_id', 'id', 'evidid'],
        'orig_time': [
            'time', 'orig_time', 'origin_time', 'origin_time_utc',
            'origin_time_iso'
        ],
        'year': ['year', 'yr', 'yyyy'],
        'month': ['month', 'mon', 'mo', 'mm'],
        'day': ['day', 'dy', 'dd'],
        'hour': ['hour', 'hr', 'h', 'hh'],
        'minute': ['minute', 'min'],
        'seconds': ['seconds', 'second', 'sec', 's', 'ss'],
        'lat': ['lat', 'latitude'],
        'lon': ['lon', 'longitude'],
        'depth': ['depth', 'depth_km'],
        'mag': ['mag', 'magnitude'],
        'mag_type': ['mag_type', 'magnitude_type']
    }
    # update the above lists with spaces instead of underscores
    for values in field_guesses.values():
        values.extend([val.replace('_', ' ') for val in values])
    output_fields = {
        # A None key must be present in the output dictionary
        None: None,
        'evid': None,
        'orig_time': None,
        'year': None,
        'month': None,
        'day': None,
        'hour': None,
        'minute': None,
        'seconds': None,
        'lat': None,
        'lon': None,
        'depth': None,
        'mag': None,
        'mag_type': None
    }
    output_field_scores = {field: 0 for field in output_fields}
    for in_field in input_fields:
        for field_name, guess_list in field_guesses.items():
            score = _field_match_score(in_field, guess_list)
            if score > output_field_scores[field_name]:
                output_field_scores[field_name] = score
                output_fields[field_name] = in_field
    if all(v is None for v in output_fields.values()):
        raise ValueError('Unable to identify any field')
    print('Columns identified ("column name" --> "identified name"):')
    for in_field, matched_field in output_fields.items():
        if in_field is None:
            continue
        if matched_field is None:
            continue
        print(f'  "{matched_field}" --> "{in_field}"')
    if (
        output_fields['orig_time'] is None
        and None in (
            output_fields['year'], output_fields['month'],
            output_fields['day'], output_fields['hour'],
            output_fields['minute'], output_fields['seconds']
        )
    ):
        raise ValueError(
            'Unable to identify all the necessary date-time fields')
    return output_fields


def _csv_file_info(filename):
    """
    Determine the delimiter and the number of rows in a CSV file.

    :param filename: input filename
    :type filename: str

    :return: a tuple with the delimiter and the number of rows
    :rtype: tuple
    """
    with open(filename, 'r', encoding='utf8') as fp:
        nrows = sum(1 for _ in fp)
        fp.seek(0)
        n_first_lines = 5
        first_lines = ''.join(fp.readline() for _ in range(n_first_lines))
        # count the number of commas and semicolons in the first n lines
        ncommas = first_lines.count(',')
        nsemicolons = first_lines.count(';')
        if ncommas >= n_first_lines:
            delimiter = ','
        elif nsemicolons >= n_first_lines:
            delimiter = ';'
        else:
            delimiter = ' '
    return delimiter, nrows


def read_catalog_from_csv(filename):
    """
    Read a catalog from a CSV file.

    :param filename: input filename
    :type filename: str

    :return: a RequakeCatalog object
    :rtype: RequakeCatalog

    :raises FileNotFoundError: if filename does not exist
    :raises ValueError: if no origin time field is found
    """
    delimiter, nrows = _csv_file_info(filename)
    with open(filename, 'r', encoding='utf8') as fp:
        reader = csv.DictReader(fp, delimiter=delimiter)
        fields = _guess_field_names(reader.fieldnames)
        nrows -= 1  # first row is the header
        cat = RequakeCatalog()
        for n, row in enumerate(reader):
            print(f'reading row {n+1}/{nrows}\r', end='')
            if fields['orig_time'] is None:
                # try build a date-time field from year, month, day, hour,
                # minute and seconds fields
                year = int_or_none(row[fields['year']])
                month = int_or_none(row[fields['month']])
                day = int_or_none(row[fields['day']])
                hour = int_or_none(row[fields['hour']])
                minute = int_or_none(row[fields['minute']])
                seconds = float_or_none(row[fields['seconds']])
                orig_time = UTCDateTime(
                    year=year, month=month, day=day,
                    hour=hour, minute=minute, second=0) + seconds
            else:
                orig_time = UTCDateTime(row[fields['orig_time']])
            row[None] = None
            ev = RequakeEvent()
            ev.orig_time = orig_time
            ev.evid = row[fields['evid']]
            if ev.evid is None:
                ev.evid = generate_evid(ev.orig_time)
            ev.lon = float_or_none(row[fields['lon']])
            ev.lat = float_or_none(row[fields['lat']])
            ev.depth = float_or_none(row[fields['depth']])
            ev.mag_type = row[fields['mag_type']]
            ev.mag = float_or_none(row[fields['mag']])
            cat.append(ev)
    print()  # needed to add a newline after the last "reading row" message
    return cat
