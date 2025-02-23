# -*- coding: utf8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Functions for waveform analysis.

:copyright:
    2021-2025 Claudio Satriano <satriano@ipgp.fr>
:license:
    GNU General Public License v3.0 or later
    (https://www.gnu.org/licenses/gpl-3.0-standalone.html)
"""
from .waveforms import (  # noqa
    get_waveform_from_client, get_event_waveform,
    get_waveform_pair, cc_waveform_pair,
    process_waveforms,
    align_pair, align_traces,
    build_template,
    NoWaveformError
)
from .station_metadata import (  # noqa
    get_traceid_coords, NoMetadataError, MetadataMismatchError
)
from .arrivals import get_arrivals  # noqa
