# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for computing P and S arrivals.

:copyright:
    2021-2024 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
import logging
from obspy.geodetics import gps2dist_azimuth, locations2degrees
from obspy.taup import TauPyModel
logger = logging.getLogger(__name__.rsplit('.', maxsplit=1)[-1])
model = TauPyModel(model='ak135')


def get_arrivals(trace_lat, trace_lon, ev_lat, ev_lon, ev_depth):
    """
    Compute P and S arrivals for a given trace and event.

    :param trace_lat: trace latitude
    :param trace_lon: trace longitude
    :param ev_lat: event latitude
    :param ev_lon: event longitude
    :param ev_depth: event depth
    :return: P and S arrivals, distance (km), distance (deg)
    :rtype: tuple
    """
    dist_deg = locations2degrees(trace_lat, trace_lon, ev_lat, ev_lon)
    distance, _, _ = gps2dist_azimuth(
        trace_lat, trace_lon, ev_lat, ev_lon)
    distance /= 1e3
    p_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['p', 'P'])
    s_arrivals = model.get_travel_times(
        source_depth_in_km=ev_depth,
        distance_in_degree=dist_deg,
        phase_list=['s', 'S'])
    return p_arrivals[0], s_arrivals[0], distance, dist_deg
