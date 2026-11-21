"""Check the managed agents are identical to the in-app agents: same instructions, model and tools.

    cd backend/agent/managed && uv run python check_parity.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


planner = load("gw_planner", HERE / "main.py")
aggregator = load("gw_aggregator", HERE.parent / "managed_aggregator" / "main.py")

from backend.agent import runner, tools  # noqa: E402  (main.py put the repo on sys.path)


def tool_names(tool_list) -> set[str]:
    return {getattr(t, "name", None) or getattr(t, "__name__", "") for t in tool_list}


PLANNER_TOOLS = [*planner.AGGREGATOR_TOOLS, planner.azure_status, planner.train_model]


checks = {
    "planner instructions identical": planner.agent.instructions == runner.AGENTS["planner"],
    "aggregator subagent instructions identical": planner.aggregator.instructions == runner.AGENTS["aggregator"],
    "standalone aggregator instructions identical": aggregator.agent.instructions == runner.AGENTS["aggregator"],
    "planner model = in-app planning model": planner.agent.model == runner.DEFAULT_MODEL,
    "planner tools = in-app planner tools": tool_names(PLANNER_TOOLS) == {s["function"]["name"] for s in tools.schemas_for("planner")},
    "aggregator tools = in-app aggregator tools": tool_names(aggregator.AGGREGATOR_TOOLS) == {s["function"]["name"] for s in tools.schemas_for("aggregator")},
}
for name, ok in checks.items():
    print(("PASS " if ok else "FAIL ") + name)
if not all(checks.values()):
    print("tools planner:", sorted(tool_names(PLANNER_TOOLS)))
    sys.exit(1)
