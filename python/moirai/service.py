"""``moirai-service <start|stop>`` for an installed wheel: runs the
moirai-service executable in the package (``moirai/bin``), which runs the
dftracer wheel's dftracer_service configured for provenance. Set
MOIRAI_SERVICE_DEBUG=1 for the _dbg build."""
import os
import sys


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    name = "moirai-service"
    if os.environ.get("MOIRAI_SERVICE_DEBUG") == "1":
        name += "_dbg"
    binary = os.path.join(here, "bin", name)
    if not os.access(binary, os.X_OK):
        sys.exit(f"moirai-service: {binary} is missing; is moirai installed "
                 "from its wheel?")
    os.execv(binary, [binary] + sys.argv[1:])


if __name__ == "__main__":
    main()
