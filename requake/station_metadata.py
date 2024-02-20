# -*- coding: utf8 -*-
"""
Functions for downloading station metadata.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    CeCILL Free Software License Agreement, Version 2.1
    (http://www.cecill.info/index.en.html)
"""
import logging
from obspy import Inventory
from obspy.clients.fdsn.header import FDSNNoDataException
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])


class NoMetadataError(Exception):
    """Exception raised for missing metadata."""


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
