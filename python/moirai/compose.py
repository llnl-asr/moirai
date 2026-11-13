"""moirai-compose: link dftracer with the modules moirai records provenance through.

dftracer's wheel ships its core alone; dftracer-modules ships its optional
modules prebuilt, and dftracer-compose links the ones this machine's libraries
need into libdftracer_core (building from source any that are not prebuilt).
moirai traces through dftracer, so run this once after installing moirai, in
the environment, and on the kind of node, it will run on (with the MPI and
HDF5 modules loaded that the application uses)::

    moirai-compose                     MPI and HDF5 as this machine has them
    moirai-compose --with-performance  also PAPI, hwloc, HIP and CUDA
    moirai-compose --check             show what it would link; change nothing

MPI and HDF5 are what moirai's provenance needs from dftracer: the files an
MPI-IO or HDF5 application reads and writes. PAPI, hwloc, HIP and CUDA are
about performance, so they are left out unless asked for. Every other option
goes to dftracer-compose as is (--status, --from-source, --source, -v, ...);
dftracer-compose --help lists them.
"""

from __future__ import annotations

import argparse
import sys

PROVENANCE = ("mpi", "hdf5")
PERFORMANCE = ("papi", "hwloc", "hip", "cuda")


def compose_args(with_performance: bool, rest: list[str]) -> list[str]:
    """The dftracer-compose arguments for moirai's modules."""
    args = ["--enable", ",".join(PROVENANCE)]
    if with_performance:
        args += ["--enable", ",".join(PERFORMANCE)]
    else:
        args += ["--disable", ",".join(PERFORMANCE)]
    return args + rest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="moirai-compose", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(__doc__.splitlines()[2:]))
    parser.add_argument("--with-performance", action="store_true",
                        help="also link " + ", ".join(PERFORMANCE))
    args, rest = parser.parse_known_args(argv)
    try:
        from dftracer import compose as dftracer_compose
    except ImportError:
        print("moirai-compose: this dftracer has no dftracer-compose; install "
              "dftracer>=2.2.0.post57.dev0 with dftracer-modules", file=sys.stderr)
        return 1
    if "--status" in rest:
        return dftracer_compose.main(rest)
    return dftracer_compose.main(compose_args(args.with_performance, rest))


if __name__ == "__main__":
    sys.exit(main())
