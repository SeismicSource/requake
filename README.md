<img src="imgs/Requake_logo.svg" width="400">

# Requake

Repeating earthquakes search and analysis.

[![changelog-badge]][changelog-link]
[![PyPI-badge]][PyPI-link]
[![license-badge]][license-link]
[![docs-badge]][docs-link]
[![DOI-badge]][DOI-link]

Copyright (c) 2021-2024 Claudio Satriano <satriano@ipgp.fr>

## Description

Requake is a command line tool to search and analyse repeating earthquakes.

It can either scan an existing earthquake catalog to search for similar events,
or perform template matching on a continuous waveform stream.

Catalogs and waveforms can be read from local files or downloaded using
standard [FDSN web services](https://www.fdsn.org/webservices/).

Requake is written in Python and uses [ObsPy](https://obspy.org) as backend.

## Installation

### Installing the latest release

#### Using pip and PyPI (preferred method)

The latest release of Requake is available on the
[Python Package Index](https://pypi.org/project/requake/).

You can install it easily through `pip`:

    pip install requake

### Installing a development snapshot

If you need a recent feature that is not in the latest release (see the
`unreleased` section in [CHANGELOG](CHANGELOG.md)), you want to use the more
recent development snapshot from the
[Requake GitHub repository](https://github.com/SeismicSource/requake).

#### Using pip

The easiest way to install the most recent development snapshot is to download
and install it through `pip`, using its builtin `git` client:

    pip install git+https://github.com/SeismicSource/requake.git

Run this command again, from times to times, to keep Requake updated with
the development version.

#### Cloning the Requake GitHub repository

If you want to take a look at the source code (and possibly modify it 😉),
clone the project using `git`:

    git clone https://github.com/SeismicSource/requake.git

or, using SSH:

    git clone git@github.com:SeismicSource/requake.git

(avoid using the "Download ZIP" option from the green "Code" button, since
version number is lost).

Then, go into the `requake` main directory and install the code in "editable
mode" by running:

    pip install -e .

You can keep your local Requake repository updated by running `git pull`
from times to times. Thanks to `pip`'s "editable mode", you don't need to
reinstall Requake after each update.

## Running

### Command line arguments

Requake is based on a single executable, aptly named `requake` 😉.

To get help, use:

    requake -h

Different commands are available:

    sample_config       write sample config file to current directory and exit
    update_config       update an existing config file to the latest version
    read_catalog        read an event catalog from web services or from a file
    print_catalog       print the event catalog to screen
    scan_catalog        scan an existing catalog for earthquake pairs
    print_pairs         print pairs to screen
    plot_pair           plot traces for a given event pair
    build_families      build families of repeating earthquakes from a catalog
                        of pairs
    print_families      print families to screen
    plot_families       plot traces for one ore more event families
    plot_timespans      plot family timespans
    plot_cumulative     cumulative plot for one or more families
    map_families        plot families on a map
    flag_family         flag a family of repeating earthquakes as valid or not
                        valid.
    build_templates     build waveform templates for one or more event
                        families
    scan_templates      scan a continuous waveform stream using one or more
                        templates

Certain commands (e.g., `plot_pair`) require further arguments (use, e.g.,
`requake plot_pair -h` to get help).

Requake supports command line tab completion for commands and arguments, thanks
to [argcomplete](https://kislyuk.github.io/argcomplete/).
To enable command line tab completion, add the following line to your `.bashrc`
or `.zshrc`:

    eval "$(register-python-argcomplete requake)"

### Typical workflow

The first thing you will want to do is to generate a sample config file:

    requake sample_config

Edit the config file according to your needs, then read or download the event
catalog:

    requake read_catalog

or

    requake read_catalog CATALOG_FILE

Now, build the catalog of event pairs with:

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

## How to Cite

If you used Requake for a scientific paper, please cite it as:

> Satriano, C. (2024). Requake: Repeating earthquakes search and analysis (X.Y).
> [doi: 10.5281/ZENODO.10832204]

Please replace `X.Y` with the Requake version number you used.

You can also cite the following abstract presented at the
2016 AGU Fall Meeting:

> Satriano, C., Doucet, A. & Bouin, M.-P. (2021).
> Probing the creep rate along the Lesser Antilles Subduction Zone through repeating earthquakes.
> In AGU Fall Meeting Abstracts
> (Vol. 2021, pp. T25A-0167), [bibcode: 2021AGUFM.T25A0167S]

<!-- Badges and project links -->
[PyPI-badge]: http://img.shields.io/pypi/v/requake.svg
[PyPI-link]: https://pypi.python.org/pypi/requake
[license-badge]: https://img.shields.io/badge/license-GPLv3-green
[license-link]: https://www.gnu.org/licenses/gpl-3.0.html
[docs-badge]: https://readthedocs.org/projects/requake/badge/?version=latest
[docs-link]: https://requake.readthedocs.io/en/latest/?badge=latest
[changelog-badge]: https://img.shields.io/badge/Changelog-136CB6.svg
[changelog-link]: https://github.com/SeismicSource/requake/blob/main/CHANGELOG.md
[DOI-badge]: https://zenodo.org/badge/DOI/10.5281/zenodo.10832204.svg
[DOI-link]: https://doi.org/10.5281/zenodo.10832204

<!-- References -->
[doi: 10.5281/ZENODO.10832204]: https://doi.org/10.5281/ZENODO.10832204
[bibcode: 2021AGUFM.T25A0167S]: https://ui.adsabs.harvard.edu/abs/2021AGUFM.T25A0167S