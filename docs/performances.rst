############
Performances
############

The runtime of a catalog scan grows with the number of event pairs, and
that number grows with the square of the catalog size.  This page gives
measured runtimes for a small catalog and for a large one on a cluster,
explains where the time goes, and shows how to estimate the runtime of
your own catalog.


Small scans
-----------

For a small catalog, the whole scan takes minutes.  On an M2 MacBook
Air, scanning 95,034 pairs downloaded from an FDSN web service took
about 5 minutes with 7 workers, that is 19,000 pairs per minute.  With
the same waveforms in the cache, the scan took 84 s, that is 68,000
pairs per minute.  In that case the runtime is dominated by the
download latency rather than by the computation, which is why
:doc:`requake wfcache prefetch <wfcache>` is the first thing to run
before a large FDSN-based scan.


A large scan on a cluster
-------------------------

The reference run scanned a catalog of 92,947 events on a single node
of the `IPGP S-CAPAD <https://www.ipgp.fr/la-recherche/services-communs/s-capad/>`_
cluster, with 64 CPU cores and 160 GB of memory.
More than 99.9% of the waveform windows were already in the on-disk
cache (see :doc:`wfcache`), so the scan read them from storage instead
of the network.  One trace was compared for each event pair.

.. list-table::
   :header-rows: 1
   :align: center
   :class: wrap-cells

   * - Quantity
     - Value
   * - Catalog events
     - 92,947
   * - Event pairs within ``catalog_search_range``
     - 461,998,043, that is 10.7% of the
       4,319,525,931 possible pairs
   * - Worker processes
     - 64
   * - Processing rate
     - 1,570 pairs/s, that is 5.7 million
       pairs per hour
   * - Wall time
     - 82 hours (3.4 days)
   * - Worker time per pair
     - 20 ms, of which 16 ms for the waveform
       retrieval and 4 ms for the cross-correlation
   * - Total CPU time
     - 2,600 core-hours
   * - Parallel efficiency
     - 49%
   * - Memory for the pair list
     - 5.5 GB in the parent process, about
       12 bytes per pair


Where the time goes
-------------------

Waveform retrieval dominates the cost of a pair: it takes 16 of the
20 ms of worker time, that is 81%.  The in-memory waveform cache serves
about half of the lookups, because consecutive pairs share their first
event, and the on-disk cache answers more than 99.9% of the remaining
ones, so the scan is not waiting for the network.

The 64 workers were busy only about half of the time: the scan
processed 1,570 pairs/s, against the 3,200 pairs/s that the workers
would sustain if they spent all their time on the 20 ms of work per
pair.  The rest of the time is spent outside the worker code, in the
parent process that distributes the pairs and writes the results to
the :doc:`output database <database_schemas>`.

A faster CPU or more workers therefore help only as long as the
storage keeps up: the number of pairs, and the speed at which the
waveforms can be read, determine the runtime.


Planning a large scan
---------------------

If a fraction :math:`r` of the :math:`N (N - 1) / 2` possible pairs
falls within ``catalog_search_range``, the scan processes

.. math::

   N_\mathrm{pairs} = r \, \frac{N (N - 1)}{2}

pairs; in the reference run :math:`r = 0.107`.  With a warm on-disk
cache, a 64-core node processes about 1,600 pairs/s, so the wall time
in hours is roughly

.. math::

   T \approx \frac{N_\mathrm{pairs}}{5.7 \times 10^6}.

About 270 million pairs fit in a two-day job limit.  A longer scan
needs a longer limit or more than one job, resuming it with
``requake scan catalog --resume`` after the job has been stopped.

The scan prints the processing rate every minute and ends with a
report that gives the total elapsed time and the average rate, so you
can compare your run with these numbers and estimate the time left
from the pairs that are still to be processed.



Family builds
-------------

``requake build families`` is fast™ with the default ``shared``
method, whose time and memory grow with the number of stored pairs
above ``cc_min``.  The ``UPGMA`` method instead needs a distance
matrix over the events linked by those pairs, so its memory use grows
with the square of their number: what counts is how many events have
a pair above ``cc_min``, not the catalog size.  For reference,
``UPGMA`` completed on a catalog of 93,000 events in which about
15,000 were linked by pairs above ``cc_min``, that is a matrix of
about 109 million distances (see :doc:`build_families`).
