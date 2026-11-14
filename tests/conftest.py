"""Set before anything else is read: the owner's commands print plain text in these tests, on a developer's machine
as on GitHub Actions, where the colour codes Typer adds would split an option's name in a command's --help."""

import os

os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
os.environ["NO_COLOR"] = "1"
