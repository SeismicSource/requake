# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Read an event catalog from a QuakeML file.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from obspy import read_events
from ..catalog.catalog import RequakeCatalog, RequakeEvent
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


def _get_evid_from_resource_id(resource_id):
    """
    Get evid from resource_id.

    :param resource_id: resource_id string
    :returns: evid string
    """
    evid = resource_id
    if '/' in evid:
        evid = resource_id.split('/')[-1]
    if '?' in evid:
        evid = resource_id.split('?')[-1]
    if '&' in evid:
        evid = evid.split('&')[0]
    if '=' in evid:
        evid = evid.split('=')[-1]
    return evid


def read_catalog_from_quakeml(filename):
    """
    Read an event catalog from a QuakeML file.

    :param filename: name of the QuakeML file
    :type filename: str

    :return: the event catalog
    :rtype: RequakeCatalog
    """
    cat = read_events(filename)
    reqcat = RequakeCatalog()
    for event in cat:
        evid = _get_evid_from_resource_id(event.resource_id.id)
        ev_creation_info = event.creation_info
        ev_contributor = (
            None if ev_creation_info is None
            else ev_creation_info.agency_id
        )
        try:
            origin = event.preferred_origin() or event.origins[0]
            orig_creation_info = origin.creation_info
            orig_author = (
                None if orig_creation_info is None
                else orig_creation_info.author
            )
            orig_time = origin.time
            lat = origin.latitude
            lon = origin.longitude
            depth = origin.depth / 1000
        except IndexError:
            logger.warning(f'Event {evid} has no origin, skipping')
            continue
        try:
            magnitude = event.preferred_magnitude() or event.magnitudes[0]
            mag = magnitude.mag
            mag_type = magnitude.magnitude_type
            mag_creation_info = magnitude.creation_info
            mag_author = (
                None if mag_creation_info is None
                else mag_creation_info.author
            )
        except IndexError:
            mag = None
            mag_type = None
            mag_author = None
        reqevent = RequakeEvent(
            evid=evid,
            orig_time=orig_time,
            lat=lat,
            lon=lon,
            depth=depth,
            mag=mag,
            mag_type=mag_type,
            mag_author=mag_author,
            author=orig_author,
            contributor=ev_contributor
        )
        reqcat.append(reqevent)
    return reqcat
