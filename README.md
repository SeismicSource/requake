# Requake

Repeating earthquakes search and analysis.

(c) 2021 - Claudio Satriano <satriano@ipgp.fr>

## Description

Requake is a command line tool to search and analyse repeating earthquakes.

It can either scan an existing earthquake catalog to search for similar events,
or perform template matching on a continuous waveform stream (*this second mode
is not yet implemented*).

Catalogs and waveforms are downloaded using standard
[FDSN web services](https://www.fdsn.org/webservices/).

Requake is written in Python and uses [ObsPy](https://obspy.org) as backend.

## Installation

### Using pip and PyPI (preferred method)

The latest release of Requake is available on the
[Python Package Index](https://pypi.org/project/requake/).

You can install it easily through `pip`:

    pip install requake


### From the Requake GitHub repository

If you need an unreleased feature, or if you want to play with the source
code, you can pull the most recent code from the
[Requake GitHub repository](https://github.com/SeismicSource/requake).

Clone the project:

    git clone https://github.com/SeismicSource/requake.git

(avoid using the "Download ZIP" option from the green "Code" button, since
version number is lost), then install the code from within the `requake` main
directory by running:

    pip install .

If you want to simultaneously modify and use the code, you can install
in "editable mode":

    pip install -e .


## Running

### Command line arguments

Requake is based on a single executable, aptly named `requake` 😉.

To get help, use:

    requake -h

The different running modes are specified as "verbs" (positional arguments).
Currently supported verbs are:

    sample_config       write sample config file to current directory and exit
    scan_catalog        scan an existing catalog for earthquake pairs
    plot_pair           plot traces for a given event pair
    build_families      build families of repeating earthquakes from a catalog
                        of pairs
    plot_families       plot traces for one ore more event families
    plot_timespans      plot family timespans
    map_families        plot families on a map
    flag_family         flag a family of repeating earthquakes as valid or not
                        valid. Note that all families are valid by default
                        when first created
    build_templates     build waveform templates for one or more event
                        families

Certain running modes (e.g., `plot_pair`) require further arguments (use, e.g.,
`requake plot_pair -h` to get help).

Requake supports command line tab completion for arguments, thanks to
[argcomplete](https://kislyuk.github.io/argcomplete/).
To enable command line tab completion, add the following line to your `.bashrc`
or `.zshrc`:

    eval "$(register-python-argcomplete requake)"

### Typical workflow

The first thing you will want to do is to generate a sample config file:

    requake sample_config

Edit the config file according to your needs, then build the catalog of event
pairs with:

    requake scan_catalog

Once done ([it will take time!](#performances)), you are ready to build
repeating earthquake families:

    requake build_families


## Performances

- `requake scan_catalog` took 53 minutes on my 2.7 GHz i7 MacBook Pro to
process 14,100,705 earthquake pairs.
Dowloaded traces are cached in memory to speed up execution. Processing is not
yet parallel: some improvements might come in future versions, when
parallelization will be implemented.

- `requake build_families` is fast™.
