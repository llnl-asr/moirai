"""``python -m moirai.agent install <harness> [--user]``: registers the hooks,
by absolute path, for the run this environment describes.

``python -m moirai.agent uninstall <harness> [--user]``: stops recording it:
takes the hooks out and cleans up after them. What was recorded stays.

``python -m moirai.agent record [options] <harness> -- <command...>``: installs
them, starts moirai-service, runs the command and stops the service
(:mod:`moirai.agent.record`)."""
import sys


def main():
    args = sys.argv[1:]
    if args[:1] == ["install"] and len(args) >= 2:
        from moirai.agent.install import install

        print(install(args[1], "user" if "--user" in args else "project"))
        return 0
    if args[:1] == ["uninstall"] and len(args) >= 2:
        from moirai.agent.install import uninstall

        path, directories = uninstall(args[1],
                                      "user" if "--user" in args else "project")
        print(path)
        for directory in directories:
            print(f"cleaned up {directory}")
        return 0
    if args[:1] == ["record"]:
        from moirai.agent.record import main as record

        return record(args[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
