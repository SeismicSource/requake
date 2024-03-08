# -*- coding: utf8 -*-
"""
Read an event catalog from web services or from a file.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
import contextlib
import urllib.request
import csv
from obspy import UTCDateTime
from obspy.clients.fdsn.header import URL_MAPPINGS
from .utils import float_or_none, int_or_none
from .catalog import (
    RequakeCatalog, RequakeEvent, generate_evid)
from .rq_setup import rq_exit
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _get_events_from_fdsnws(
        baseurl,
        starttime=None, endtime=None,
        minlatitude=None, maxlatitude=None,
        minlongitude=None, maxlongitude=None,
        latitude=None, longitude=None, minradius=None, maxradius=None,
        mindepth=None, maxdepth=None,
        minmagnitude=None, maxmagnitude=None,
        eventid=None):
    """
    Download from a fdsn-event webservice using text format.

    :param baseurl: base URL of the fdsn-event webservice
    :type baseurl: str
    :param starttime: start time
    :type starttime: obspy.UTCDateTime or str
    :param endtime: end time
    :type endtime: obspy.UTCDateTime or str
    :param minlatitude: minimum latitude
    :type minlatitude: float
    :param maxlatitude: maximum latitude
    :type maxlatitude: float
    :param minlongitude: minimum longitude
    :type minlongitude: float
    :param maxlongitude: maximum longitude
    :type maxlongitude: float
    :param latitude: latitude of radius center
    :type latitude: float
    :param longitude: longitude of radius center
    :type longitude: float
    :param minradius: minimum radius
    :type minradius: float
    :param maxradius: maximum radius
    :type maxradius: float
    :param mindepth: minimum depth
    :type mindepth: float
    :param maxdepth: maximum depth
    :type maxdepth: float
    :param minmagnitude: minimum magnitude
    :type minmagnitude: float
    :param maxmagnitude: maximum magnitude
    :type maxmagnitude: float

    :return: a RequakeCatalog object
    :rtype: RequakeCatalog
    """
    # pylint: disable=unused-argument
    arguments = locals()
    query = 'query?format=text&nodata=404&'
    for key, val in arguments.items():
        if key in ['baseurl']:
            continue
        if val is None:
            continue
        if isinstance(val, UTCDateTime):
            val = val.strftime('%Y-%m-%dT%H:%M:%S')
        query += f'{key}={val}&'
    # remove last "&" symbol
    query = query[:-1]
    # see if baseurl is an alias defined in ObsPy
    with contextlib.suppress(KeyError):
        baseurl = URL_MAPPINGS[baseurl]
    baseurl = f'{baseurl}/fdsnws/event/1/'
    url = baseurl + query
    logger.info(f'Requesting {url}...')
    cat = RequakeCatalog()
    with urllib.request.urlopen(url) as f:
        content = f.read().decode('utf-8')
    for line in content.split('\n'):
        if not line:
            continue
        if line[0] == '#':
            continue
        try:
            ev = RequakeEvent()
            ev.from_fdsn_text(line)
        except ValueError:
            continue
        cat.append(ev)
    return cat


def _read_catalog_from_fdsnws(config):
    """
    Read an event catalog from FDSN web services.

    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Event catalog.
    :rtype: requake.catalog.RequakeCatalog
    """
    logger.info('Downloading events from FDSN web services...')
    cat_info = zip(
        config.catalog_fdsn_event_urls,
        config.catalog_start_times,
        config.catalog_end_times)
    event_list = []
    for url, start_time, end_time in cat_info:
        try:
            event_list += _get_events_from_fdsnws(
                url,
                starttime=start_time, endtime=end_time,
                minlatitude=config.catalog_lat_min,
                maxlatitude=config.catalog_lat_max,
                minlongitude=config.catalog_lon_min,
                maxlongitude=config.catalog_lon_max,
                mindepth=config.catalog_depth_min,
                maxdepth=config.catalog_depth_max,
                minmagnitude=config.catalog_mag_min,
                maxmagnitude=config.catalog_mag_max
            )
        except Exception as m:
            logger.warning(
                f'Unable to download events from {url} for period '
                f'{start_time} - {end_time}. {m}'
            )
    catalog = RequakeCatalog(event_list)
    logger.info(f'{len(catalog)} events downloaded')
    return catalog


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


def _read_csv_catalog_file(filename):
    """
    Read events in CSV file format.

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


def _read_catalog_from_file(config):
    """
    Read an event catalog from a file.

    Supported formats are FDSN text and CSV.

    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Event catalog.
    :rtype: requake.catalog.RequakeCatalog

    :raises FileNotFoundError: if the file does not exist
    :raises ValueError: if the file format is not supported
    """
    catalog_file = config.args.catalog_file
    # try to read the catalog as a FDSN text file
    with contextlib.suppress(ValueError):
        cat = RequakeCatalog()
        cat.read(catalog_file)
        return cat
    # try to read the catalog as a CSV file
    # raises ValueError in case of failure
    return _read_csv_catalog_file(catalog_file)


def read_catalog(config):
    """
    Read an event catalog from web services or from a file.

    Write the catalog to the output directory.

    :param config: Configuration object.
    :type config: requake.rq_setup.RequakeConfig
    :return: Event catalog.
    :rtype: requake.catalog.RequakeCatalog
    """
    catalog = RequakeCatalog()
    out_cat_file = config.scan_catalog_file
    nevs_read = 0
    if config.args.append:
        with contextlib.suppress(FileNotFoundError):
            catalog = RequakeCatalog()
            catalog.read(out_cat_file)
            nevs_read = len(catalog)
            logger.info(f'{nevs_read} events read from "{out_cat_file}"')
    logger.info('Reading catalog...')
    in_cat_file = config.args.catalog_file
    if in_cat_file is not None:
        try:
            catalog += _read_catalog_from_file(config)
        except FileNotFoundError:
            logger.error(f'File "{in_cat_file}" not found')
            rq_exit(1)
        except ValueError as m:
            logger.error(f'Error reading catalog file "{in_cat_file}": {m}')
            rq_exit(1)
    else:
        catalog += _read_catalog_from_fdsnws(config)
    if not catalog:
        logger.error('No event read')
        rq_exit(1)
    catalog.deduplicate()
    # Sort catalog in increasing time order
    catalog.sort()
    # Write catalog to output file
    catalog.write(out_cat_file)
    nevs_written = len(catalog) - nevs_read
    logger.info(f'{nevs_written} events written to "{out_cat_file}"')
