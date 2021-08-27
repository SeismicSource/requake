# Requake

Repeating earthquakes search and analysis.

(c) 2021 - Claudio Satriano <satriano@ipgp.fr>

## Description

Requake is a command line tool to search and analyse repeating earthquakes.

It can either scan an existing earthquake catalog to search for similar events,
or perform template matching on a continuous waveform stream (*this second mode
is not yet implemented*).

Requake is written in Python and uses [ObsPy](https://obspy.org) as backend.

## Installation

### From the Requake GitHub repository

Clone the project:

    git clone https://github.com/SeismicSource/requake.git

(avoid using the "Download ZIP" option from the green "Code" button, since
version number is lost), then install the code from within the `requake` main
directory by running:

    pip install .

## Running

Requake is based on a single executable, aptly named `requake` 😉.

To get help, use:

    requake -h

The different running modes are specified as "verbs" (positional arguments).
Currently supported verbs are:

    requake sample_config       write sample config file to current
                                directory and exit
    requake scan_catalog        scan an existing catalog for earthquake
                                pairs
    requake scan_template       scan a continuous waveform stream using
                                a template
    requake plot_pair           plot traces for a given event pair
    requake build_families      build families of repeating earthquakes
                                from a catalog of pairs

Certain running modes (e.g., `plot_pair`) require further arguments (use, e.g.,
`requake plot_pair -h` to get help).
