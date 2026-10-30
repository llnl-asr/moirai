============
Trace format
============

moirai's records and events are dftracer JSON lines (see dftracer's trace
format), on moirai's own dftracer layer: ``"type":128``. They are the same
records dftracer's former provenance API wrote, so existing tools read them.

------------------------------------------
Records
------------------------------------------

Metadata records (``"ph":4``), written once per process for entities and
entity types:

.. code-block:: json

   {"name":"ET","cat":"dftracer","type":128,"pid":1,"tid":1,"ph":4,
    "args":{"hhash":"...","type":"dataset","role":1,"description":"raw input"}}
   {"name":"EH","cat":"dftracer","type":128,"pid":1,"tid":1,"ph":4,
    "args":{"hhash":"...","id":"638549b593275bd7","type":"dataset","store":3,
            "uri":"file:///data/in0.h5"}}
   {"name":"ER","cat":"dftracer","type":128,"pid":1,"tid":1,"ph":4,
    "args":{"hhash":"...","relation":16,"subject":"9a1c...","object":"6385..."}}

Field order within ``args`` is not fixed.

------------------------------------------
Activities
------------------------------------------

Complete events (``"ph":1``) in category ``moirai``, never aggregated:

.. code-block:: json

   {"id":7,"name":"train","cat":"moirai","type":128,"pid":1,"tid":1,
    "ts":1793325918816079,"dur":1203,"ph":1,
    "args":{"hhash":"...","relations":{"used":["638549b593275bd7"],
                                       "generated":["9a1c..."]}}}

------------------------------------------
Values
------------------------------------------

Ids
   16 lowercase hex digits of the 64-bit FNV-1a hash of the sanitized type,
   a ``0x1f`` byte and the key. 0 is never an id.

``store``
   0 memory, 1 GPU memory, 2 local disk, 3 parallel file system, 4 burst
   buffer, 5 object store, 6 database, 7 network, 8 other.

``role``
   0 unknown, 1 input, 2 output, 3 intermediate, 4 parameter, 5 reference.

``relation`` (``ER``) and relation names (activities)
   Activity relations: ``used`` (0), ``generated`` (1), ``invalidated`` (2),
   ``updated`` (3). Entity relations: ``derived_from`` (16),
   ``revision_of`` (17), ``contains`` (18), ``part_of`` (19),
   ``specialization_of`` (20), ``alternate_of`` (21), ``depends_on`` (22).
