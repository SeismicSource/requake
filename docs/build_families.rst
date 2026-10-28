.. _build_families:

#################
Building Families
#################

``requake build families`` groups the events connected by similar
waveforms into *families* of repeating earthquakes.  It reads the
:doc:`event pairs <pairs>` of a :doc:`catalog scan <scan_catalog>` and
stores the result, called a *family build*, in the
:doc:`output database <database_schemas>`, together with the clustering
method and its parameters.

The command reads the pairs of the scan selected with ``--scan-id``
(the latest one by default) and stores its result under a new family
build id.  Use ``-l``/``--label`` to name the build.

The same pair table can be clustered in different ways, and each build
keeps its own family numbering:

.. code-block::

   requake build families --scan-id 1 -l "shared"
   requake build families --scan-id 1 -l "UPGMA"


Clustering methods
------------------

The method is set with ``clustering_algorithm`` in the configuration
file, and both methods only use the event pairs with
``cc >= cc_min``: the weaker pairs are never read from the database.

``shared``
   Two events belong to the same family when a pair above ``cc_min``
   links them, directly or through a chain of other events.  Because
   the relation is transitive, a family can contain events whose own
   pair is below ``cc_min``.

``UPGMA``
   Families are cut from a dendrogram built with the Unweighted Pair
   Group Method with Arithmetic Mean (UPGMA), at a distance of
   ``1 - cc_min``.  Only the events linked by at least one pair above
   ``cc_min`` take part, and two events without such a pair are
   treated as maximally distant, so a chain of pairs cannot group
   them by itself.

``UPGMA`` needs a distance matrix that grows with the square of the
number of events, so it is only practical on catalogs with a few
thousand events; ``shared`` is the default and the recommended choice
for large ones.


Replacing a build
-----------------

When a build with identical parameters already exists, Requake asks
whether to replace it or to add a new build; ``-f``/``--force``
replaces it without asking.  A replaced build keeps its id, while its
families and template detections are removed.


Using a build
-------------

Every command that reads families (``print families``,
``plot families``, ``plot timespans``, ``plot cumulative``,
``plot map``, ``flag family``, ``build templates``,
``scan templates``) uses the latest build, unless another one is
selected with ``--build-id``:

.. code-block::

   requake print families --build-id 2
   requake flag family --build-id 2 7 false

``requake list builds`` shows the stored builds, with the scan and the
clustering method each of them used.
