# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for downloading station metadata.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from obspy import Inventory
from obspy.clients.fdsn.header import FDSNNoDataException
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class NoMetadataError(Exception):
    """Exception raised for missing metadata."""


class MetadataMismatchError(Exception):
    """Exception raised for mismatched metadata."""


def get_metadata(config):
    """
    Download metadata for the trace_ids specified in config file.

    The metadata is stored in the config object.

    :param config: a Config object
    :type config: config.Config
    """
    logger.info('Downloading station metadata...')
    inv = Inventory()
    cl = config.fdsn_station_client
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
        except FDSNNoDataException as m:
            msg = str(m).replace('\n', ' ')
            raise NoMetadataError(
                f'Unable to download metadata for trace id: {trace_id}.\n'
                f'Error message: {msg}'
            ) from m
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


def get_traceid_coords(config, orig_time=None):
    """
    Get coordinates for the trace_ids specified in config file.

    :param config: a Config object
    :type config: config.Config
    :param orig_time: origin time
    :type orig_time: obspy.UTCDateTime
    :return: a dictionary with trace_id as key and coordinates as value
    :rtype: dict

    :raises MetadataMismatchError: if coordinates are not found
    """
    if config.inventory is None:
        get_metadata(config)
    traceid_coords = {}
    for trace_id in config.catalog_trace_id:
        try:
            coords = config.inventory.get_coordinates(trace_id, orig_time)
        except Exception as m:
            # note: get_coordinaets raises a generic Exception
            raise MetadataMismatchError(
                f'Unable to find coordinates for trace {trace_id} '
                f'at time {orig_time}'
            ) from m
        traceid_coords[trace_id] = coords
    return traceid_coords
