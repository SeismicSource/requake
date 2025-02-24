# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for downloading station metadata.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
import csv
from obspy import read_inventory
from obspy.core.inventory import Inventory, Network, Station, Channel
from obspy.clients.fdsn.header import FDSNNoDataException
from ..config import config
from ..formulas import float_or_none, guess_field_names
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class NoMetadataError(Exception):
    """Exception raised for missing metadata."""


class MetadataMismatchError(Exception):
    """Exception raised for mismatched metadata."""


def _read_station_metadata_from_csv(csv_file):
    """
    Read station metadata from a CSV file.

    The inventory is stored in the config object.

    :param csv_file: path to the CSV file
    :type csv_file: str

    :returns: inventory
    :rtype: obspy.Inventory
    """
    inv = Inventory()
    with open(csv_file, 'r', encoding='utf8') as fp:
        reader = csv.DictReader(fp, skipinitialspace=True)
        fieldnames = reader.fieldnames
        field_guesses = {
            'network': ['network', 'net', 'netw'],
            'station': ['station', 'sta', 'stat', 'name'],
            'location': ['location', 'loc', 'locat'],
            'channel': ['channel', 'chan', 'ch'],
            'longitude': ['longitude', 'lon', 'long'],
            'latitude': ['latitude', 'lat'],
            'elevation': ['elevation', 'elev', 'elevat'],
            'depth': ['depth', 'dep'],
        }
        guess_field_names(fieldnames, field_guesses)
        networks = []
        stations = []
        for row in reader:
            row[None] = None
            # use '@@' for empty network codes
            net = row[field_guesses['network']] or '@@'
            net = net.replace('.', '_')
            # see if the network already exists in the networks list
            network = next((n for n in networks if n.code == net), None)
            if network is None:
                network = Network(code=net)
                networks.append(network)
                inv.networks.append(network)
            sta = row[field_guesses['station']]
            if sta is None:
                logger.warning('Station code is missing')
                continue
            loc = row[field_guesses['location']] or ''
            chan = row[field_guesses['channel']] or ''
            # replace dots with underscores
            sta = sta.replace('.', '_')
            loc = loc.replace('.', '_')
            chan = chan.replace('.', '_')
            lon = float_or_none(row[field_guesses['longitude']]) or 0
            lat = float_or_none(row[field_guesses['latitude']]) or 0
            elev = float_or_none(row[field_guesses['elevation']]) or 0
            depth = float_or_none(row[field_guesses['depth']]) or 0
            # see if the station already exists in the stations list
            station = next((s for s in stations if s.code == sta), None)
            if station is None:
                station = Station(
                    code=sta, latitude=lat, longitude=lon, elevation=elev)
                network.stations.append(station)
            channel = Channel(
                code=chan, location_code=loc, latitude=lat, longitude=lon,
                elevation=elev, depth=depth
            )
            station.channels.append(channel)
    return inv


def _read_station_metadata():
    """
    Read station metadata from a file or dir path defined in the config.

    The inventory is stored in the config object.
    """
    smd_path = config.station_metadata_path
    if smd_path is None:
        config.inventory = None
        return
    try:
        config.inventory = read_inventory(smd_path)
    except (FileNotFoundError, TypeError):
        try:
            config.inventory = _read_station_metadata_from_csv(smd_path)
        except (FileNotFoundError, TypeError) as err:
            raise NoMetadataError(
                f'Unable to read station metadata from local path: {smd_path}'
            ) from err
    logger.info(f'Reading station metadata from local path: {smd_path}')


def _download_metadata():
    """
    Download metadata for the trace_ids specified in config file.

    The metadata is stored in the config object.
    """
    logger.info('Downloading station metadata...')
    inv = Inventory()
    cl = config.station_client
    start_time = min(config.catalog_start_times)
    end_time = max(config.catalog_end_times)
    if config.args.traceid is not None:
        trace_ids = [config.args.traceid, ]
    else:
        trace_ids = config.catalog_trace_id
    for trace_id in trace_ids:
        net, sta, loc, chan = trace_id.split('.')
        try:
            inv += cl.get_stations(
                network=net, station=sta, location=loc, channel=chan,
                starttime=start_time, endtime=end_time, level='channel'
            )
        except FDSNNoDataException as err:
            msg = str(err).replace('\n', ' ')
            raise NoMetadataError(
                f'Unable to download metadata for trace id: {trace_id}.\n'
                f'Error message: {msg}'
            ) from err
    channels = inv.get_contents()['channels']
    unique_channels = set(channels)
    channel_count = [channels.count(id) for id in unique_channels]
    for channel, count in zip(unique_channels, channel_count):
        if count > 1:
            logger.warning(
                f'Channel {channel} is present {count} times in inventory')
    config.inventory = inv
    logger.info(
        'Metadata downloaded for channels: '
        f"{set(config.inventory.get_contents()['channels'])}"
    )


def get_traceid_coords_old(orig_time=None):
    """
    Get coordinates for the trace_ids specified in config file.

    :param orig_time: origin time
    :type orig_time: obspy.UTCDateTime
    :return: a dictionary with trace_id as key and coordinates as value
    :rtype: dict

    :raises MetadataMismatchError: if coordinates are not found
    """
    if config.inventory is None:
        _read_station_metadata()
    if config.inventory is None:
        _download_metadata()
    traceid_coords = {}
    for trace_id in config.catalog_trace_id:
        net, sta, loc, chan = trace_id.split('.')
        net = net or '@@'
        _trace_id = f'{net}.{sta}.{loc}.{chan}'
        try:
            coords = config.inventory.get_coordinates(_trace_id, orig_time)
        # pylint: disable=broad-except
        except Exception:
            # note: get_coordinaets raises a generic Exception
            # try again with empty channel code
            try:
                _trace_id = f'{net}.{sta}.{loc}.'
                coords = config.inventory.get_coordinates(_trace_id, orig_time)
            except Exception as err:
                raise MetadataMismatchError(
                    f'Unable to find coordinates for trace {trace_id} '
                    f'at time {orig_time}'
                ) from err
        traceid_coords[trace_id] = coords
    return traceid_coords


def _fetch_coordinates(net, sta, loc, chan, orig_time):
    """
    Fetch coordinates for a trace_id at a given time.

    Attempt to retrieve coordinates, first with full trace_id,
    then without channel.

    :param net: network code
    :type net: str
    :param sta: station code
    :type sta: str
    :param loc: location code
    :type loc: str
    :param chan: channel code
    :type chan: str
    :param orig_time: origin time
    :type orig_time: obspy.UTCDateTime

    :return: coordinates or None
    :rtype: dict
    """
    for ch in [chan, '']:
        _trace_id = f'{net}.{sta}.{loc}.{ch}'
        try:
            return config.inventory.get_coordinates(_trace_id, orig_time)
        # pylint: disable=broad-except
        # note: get_coordinaets raises a generic Exception
        except Exception:
            # Try next option if it fails
            continue
    # If both attempts fail, return None
    return None


def get_traceid_coords(orig_time=None):
    """
    Get coordinates for the trace_ids specified in config file or from args.

    :param orig_time: origin time
    :type orig_time: obspy.UTCDateTime
    :return: a dictionary with trace_id as key and coordinates as value
    :rtype: dict

    :raises MetadataMismatchError: if coordinates are not found
    """
    if config.inventory is None:
        _read_station_metadata()
    if config.inventory is None:
        _download_metadata()
    traceid_coords = {}
    traceid_list = config.catalog_trace_id
    if config.args.traceid is not None:
        traceid_list.append(config.args.traceid)
    for trace_id in traceid_list:
        net, sta, loc, chan = trace_id.split('.')
        net = net or '@@'
        coords = _fetch_coordinates(net, sta, loc, chan, orig_time)
        if coords is None:
            raise MetadataMismatchError(
                f'Unable to find coordinates for trace {trace_id} '
                f'at time {orig_time}'
            )
        traceid_coords[trace_id] = coords
    return traceid_coords
