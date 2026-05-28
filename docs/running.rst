Running
-------

Command line arguments
^^^^^^^^^^^^^^^^^^^^^^

Requake is based on a single executable, aptly named ``requake`` 😉.

To get help, use:

.. code-block::

   requake -h


Different commands are available:

.. code-block:: text

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


Certain commands (e.g., ``plot_pair``\ ) require further arguments
(use, e.g., ``requake plot_pair -h`` to get help).

Requake supports command line tab completion for commands and arguments, thanks
to `argcomplete <https://kislyuk.github.io/argcomplete/>`_.
To enable command line tab completion run:

.. code-block::

    activate-global-python-argcomplete


(This is a one-time command that needs to be run only once).

Or, alternatively, add the following line to your ``.bashrc`` or ``.zshrc``:

.. code-block::

    eval "$(register-python-argcomplete requake)"


Typical workflow
^^^^^^^^^^^^^^^^

The first thing you will want to do is to generate a sample
:ref:`configuration_file`:

.. code-block::

   requake sample_config


Edit the :ref:`configuration_file` according to your needs, then read or
download the event catalog:

.. code-block::

   requake read_catalog


or

.. code-block::

   requake read_catalog CATALOG_FILE


Now, build the catalog of event pairs with:

.. code-block::

   requake scan_catalog


Once done (\ `it will take time! <performances.html#performances>`_\ ),
you are ready to build repeating earthquake families:

.. code-block::

   requake build_families


Migrating Legacy Pair Databases
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you already have an older ``requake.sqlite`` with the legacy
``event_pairs`` layout (text columns ``evid1/evid2/trace_id``), first use the
legacy-to-compact migration helper:

.. code-block::

   python .vscode/migrate_pairs_schema.py \
       --config .vscode/migrate_pairs_schema.ini

By default, lag consistency mismatches are reported as warnings and migration
continues with ``lag_samples`` as the authoritative value. Use
``--strict-lag-check`` to fail on any mismatch.

To convert an existing compact database to the integer-key pair schema
(``event1_id/event2_id/trace_key_id``), run:

.. code-block::

   python .vscode/migrate_pairs_integer_keys.py \
      --db /path/to/requake.sqlite

By default this migration creates a timestamped backup and compacts the
database with ``VACUUM`` after conversion.

