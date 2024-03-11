# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Read an event catalog from FDNS web services.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import contextlib
import urllib.request
from obspy import UTCDateTime
from obspy.clients.fdsn.header import URL_MAPPINGS
from ..catalog.catalog import RequakeCatalog, RequakeEvent
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


def read_catalog_from_fdsnws(config):
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
