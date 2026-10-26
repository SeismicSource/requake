.. _pager:

#################
Interactive Pager
#################

All ``print_`` commands (``print_catalog``, ``print_pairs``,
``print_families``) open an interactive `curses
<https://en.wikipedia.org/wiki/Curses_(programming_library)>`_ pager
when the output is a terminal.  Use ``--no-pager`` to fall back to
plain-text output (e.g., for piping to ``wc`` or ``grep``).  Requesting
a specific output format with ``-f``/``--format`` implies
``--no-pager``, since the pager draws the table with its own layout and
ignores the output format.


Navigation
----------

============= ===========================================
Key           Action
============= ===========================================
``↓`` ``↑``   Move selection down / up one row
``j`` ``k``   Same as ``↓`` / ``↑`` (vim-style)
``Space``     Page down
``f``         Page down
``b``         Page up
``g``         Jump to first row (home)
``G``         Jump to last row (end)
``Enter``     Show row details in a popup
``←`` ``→``   Scroll horizontally
``⇧←``        Jump to beginning of line
``⇧→``        Jump to end of line
``⇧↑``        Page up
``⇧↓``        Page down
============= ===========================================


Sorting
-------

============= ===========================================
Key           Action
============= ===========================================
``1``-``9``   Sort by column (1 = first, 9 = ninth)
``0``         Restore default sort order
``s``         Open interactive sort column selector
============= ===========================================


Clipboard
---------

Pressing ``c`` copies the selected row's identifier(s) to the system
clipboard.  For the pairs table both event IDs are copied
(space-separated).


Pairs large-dataset warning
---------------------------

When more than 10,000 pairs match the current filter, ``print_pairs``
shows a confirmation prompt before opening the pager.  Use
``--cc-min`` / ``--cc-max`` to narrow the selection, or ``--force``
to skip the warning.


Invalid pairs
-------------

``print_pairs`` shows only valid pairs.  Pairs flagged as invalid (see
:doc:`pairs`), i.e. pairs involving an event marked as duplicate, are
hidden.  Use ``--include-invalid`` to list them as well; an ``invalid``
column is then added to the table, and the table can be sorted on it to
show the invalid pairs first.
