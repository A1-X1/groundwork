"""Create or update the Groundwork Planner agent in your Mistral account.

    python -m backend.agent.setup            # create, or update if already registered

The agent's id is saved to data/processed/mistral_agent.json. Tool calls are executed by
Groundwork (backend.agent.tools), so the hosted agent is the same brain as the local
runner: use it from Mistral's console/Conversations API, or let Groundwork call it.
"""

from __future__ import annotations

import json

from backend.scoring.data import PROCESSED_DIR

from .runner import DEFAULT_MODEL, INSTRUCTIONS, _client
from .tools import SCHEMAS

AGENT_FILE = PROCESSED_DIR / "mistral_agent.json"
NAME = "Groundwork Planner"
DESCRIPTION = ("Plans a new site-suitability use case in Groundwork: data layers, scoring profile, 3D model "
               "and an Azure ML feasibility model, then shows the best sites.")


def main() -> None:
    client = _client()
    saved = json.loads(AGENT_FILE.read_text()) if AGENT_FILE.exists() else {}
    kwargs = {"model": DEFAULT_MODEL, "name": NAME, "description": DESCRIPTION,
              "instructions": INSTRUCTIONS, "tools": SCHEMAS, "completion_args": {"temperature": 0.2}}
    if saved.get("id"):
        agent = client.beta.agents.update(agent_id=saved["id"], **kwargs)
        verb = "updated"
    else:
        agent = client.beta.agents.create(**kwargs)
        verb = "created"
    AGENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_FILE.write_text(json.dumps({"id": agent.id, "name": agent.name, "model": agent.model,
                                      "version": getattr(agent, "version", None)}, indent=2) + "\n")
    print(f"{verb} Mistral agent {agent.name!r} ({agent.id}) on {agent.model}")


if __name__ == "__main__":
    main()
