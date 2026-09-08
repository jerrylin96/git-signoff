"""CLI entry point for `git-signoff init`."""

import sys
from git_signoff import init


def main() -> int:
    # If invoked as `git-signoff init ...`, strip the `init` subcommand from sys.argv
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        sys.argv.pop(1)
    return init.main()


if __name__ == "__main__":
    sys.exit(main())
