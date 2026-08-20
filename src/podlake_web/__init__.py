"""podlake-web: build public Tier-1 analytics extracts from a podlake DuckLake."""

# `tasks` is imported for its side effect: it registers check/site/build/install/
# refresh on the same Typer app that build.py defines, so one `podlake-web` command
# covers the whole repository. The dependency runs one way only — tasks imports
# build, never the reverse — which is why this lives here rather than in build.py,
# where it would be a cycle.
from podlake_web import tasks as _tasks  # noqa: F401  (registers task commands)
from podlake_web.build import app

__all__ = ["app"]
