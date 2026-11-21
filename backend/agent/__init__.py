"""Groundwork planning agent (Mistral tool calling + Azure ML training).

    from backend.agent import run
    run("I'm looking for building a nuclear power plant", on_event=print)
"""

from .runner import run

__all__ = ["run"]
