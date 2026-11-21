"""Groundwork Data Aggregator as its own Mistral managed agent (shows separately in Studio).

    cd backend/agent/managed_aggregator
    uv run agents chat
    uv run agents serve

Same tools and instructions as the Aggregator subagent inside the Planner
(backend/agent/managed/main.py); this project just registers it on its own.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("groundwork_planner_agent", HERE.parent / "managed" / "main.py")
planner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(planner)  # the planner project's module: shared tools + paths

agents = planner.agents
AGENT_DIR, AGGREGATOR_TOOLS, MODEL = planner.AGENT_DIR, planner.AGGREGATOR_TOOLS, planner.MODEL

agent = agents.Agent(
    model=MODEL,
    name="groundwork-data-aggregator",
    description=("Builds a new Groundwork use case from aggregated free data, with no ML training: layers for "
                 "one city region, weight notes from local data ranges, a 3D model and the best sites."),
    instructions=(AGENT_DIR / "aggregator.md").read_text(),
    temperature=0.2,
    tools=AGGREGATOR_TOOLS,
)
