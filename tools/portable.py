"""Launch the workbench on double click, preserving all CLI subcommands."""

import sys

from pixeltoolkit.cli import main


if __name__ == "__main__":
    main(sys.argv[1:] or ["gui"])
