"""Groundwork's agents as Mistral managed agents (mistralai-agents SDK).

    cd backend/agent/managed
    uv run agents chat        # talk to the Planner in this terminal
    uv run agents serve       # run here and register in your Mistral workspace (shows in Studio)

The Planner is the main agent; the Data Aggregator is its subagent, used when Azure ML isn't
connected. Every tool wraps the same function the in-app runner uses (backend/agent/tools.py),
so both paths behave identically. Instructions come from backend/agent/*.md.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from mistralai import agents  # noqa: E402

from backend.agent import runner as gw_runner  # noqa: E402
from backend.agent import tools as gw  # noqa: E402

AGENT_DIR = REPO / "backend" / "agent"
# Same planning model and the SAME instruction text as the in-app runner (one source of truth).
MODEL = gw_runner.DEFAULT_MODEL
PLANNER_INSTRUCTIONS = gw_runner.INSTRUCTIONS
AGGREGATOR_INSTRUCTIONS = gw_runner.AGGREGATOR_INSTRUCTIONS


async def _call(name: str, **kwargs: Any) -> dict[str, Any]:
    """Run a Groundwork tool off the event loop; errors come back as {"error": …}."""
    args = {k: v for k, v in kwargs.items() if v is not None}
    return await asyncio.to_thread(gw.call, name, args)


@agents.tool
async def get_catalog() -> dict[str, Any]:
    """List Groundwork's layers ([SYNTHETIC] marks placeholders), profiles, regions, positives sources, UI commands and Azure ML status. Call first."""
    return await _call("get_catalog")


@agents.tool
async def search_data_sources(query: str) -> dict[str, Any]:
    """Search the vetted registry of free data sources that can be added as new layers."""
    return await _call("search_data_sources", query=query)


@agents.tool
async def add_layer(id: str, label: str, unit: str, kind: str, description: str, template: str,
                    params: dict[str, Any], is_mask: bool = False) -> dict[str, Any]:
    """Add a data layer from a registry template (no code). kind: raster|proximity|aggregate. template: osm_proximity|osm_share (params {selectors:[Overpass selectors]}), openmeteo_daily ({variable, aggregate}), usgs_earthquakes ({min_magnitude, years, radius_km}). Then call build_layers."""
    return await _call("add_layer", id=id, label=label, unit=unit, kind=kind, description=description,
                       template=template, params=params, is_mask=is_mask)


@agents.tool
async def build_layers(layer_ids: list[str], region: str = "london") -> dict[str, Any]:
    """Download and compute layers for ONE region only (the one the user is working in). Returns real/synthetic/unavailable per layer."""
    return await _call("build_layers", layer_ids=layer_ids, region=region)


@agents.tool
async def layer_stats(layer_ids: list[str], region: str = "london") -> dict[str, Any]:
    """Typical values (p10/median/p90), unit and data status of layers in a region, to judge what 'more' means locally."""
    return await _call("layer_stats", layer_ids=layer_ids, region=region)


@agents.tool
async def create_profile(id: str, label: str, description: str, layers: dict[str, dict[str, Any]],
                         masks: list[str] | None = None, model: dict[str, Any] | None = None,
                         notes: dict[str, str] | None = None) -> dict[str, Any]:
    """Create a use-case profile. layers: {layer_id: {weight: number>0, better: 'higher'|'lower'}}. masks: hard exclusions. model: optional presence model {type:'presence', positives:'osm:key=value', exclude_features, floor}. notes: {layer_id: one sentence on what its weight means}."""
    return await _call("create_profile", id=id, label=label, description=description, layers=layers,
                       masks=masks, model=model, notes=notes)


@agents.tool
async def design_3d_model(spec: dict[str, Any]) -> dict[str, Any]:
    """Save a parametric low-poly 3D model (three.js-rendered JSON): {id (= profile id), label, footprint_m:[w,d], parts:[{shape: box|cylinder|cone|dome|hyperboloid, position:[x,y,z], rotation_y, rotation_z, color, size|radius|height|radius_bottom|radius_waist|radius_top|waist_at}]}, metres, y up, ≤5000 triangles."""
    return await _call("design_3d_model", spec=spec)


@agents.tool
async def azure_status() -> dict[str, Any]:
    """Check whether an Azure ML workspace is connected. Always call before training."""
    return await _call("azure_status")


@agents.tool
async def train_model(profile_id: str, backend: str = "auto") -> dict[str, Any]:
    """Train the profile's feasibility model: 'azure' (Azure ML job), 'local', or 'auto'. If Azure isn't connected it returns action_required=choose_training."""
    return await _call("train_model", profile_id=profile_id, backend=backend)


@agents.tool
async def preview_scores(profile_id: str, top_n: int = 5) -> dict[str, Any]:
    """Score a profile and return the best sites with named areas and top drivers, to verify results."""
    return await _call("preview_scores", profile_id=profile_id, top_n=top_n)


@agents.tool
async def ui_command(commands: list[dict[str, Any]]) -> dict[str, Any]:
    """Send an ORDERED queue of Groundwork map commands ({command: NAME, ...args}), e.g. PAN_CITY, SET_PROFILE, SHOW_TOP_SITES, CREATE_STRUCTURE."""
    return await _call("ui_command", commands=commands)


@agents.tool
async def request_user_action(action: str, message: str) -> dict[str, Any]:
    """Ask the user to do something only they can: connect_azure | choose_training | connect_mistral | confirm | provide_api_key."""
    return await _call("request_user_action", action=action, message=message)


@agents.tool
async def find_address(query: str | None = None, lat: float | None = None, lon: float | None = None) -> dict[str, Any]:
    """Look up an address: `query` (e.g. '10 Downing Street, London') → full address + coordinates, or `lat`+`lon` → the street address there. Then fly there with PAN_ADDRESS."""
    return await _call("find_address", query=query, lat=lat, lon=lon)


AGGREGATOR_TOOLS = [find_address, get_catalog, search_data_sources, add_layer, build_layers, layer_stats, create_profile,
                    design_3d_model, preview_scores, ui_command, request_user_action]

aggregator = agents.Subagent(
    name="groundwork-data-aggregator",
    description=("Builds a new Groundwork use case from aggregated free data, with no ML training, when Azure ML "
                 "isn't connected and the user chose the aggregator: layers, weight notes, 3D model, best sites."),
    instructions=AGGREGATOR_INSTRUCTIONS,
    model=MODEL,
    temperature=0.2,
    tools=AGGREGATOR_TOOLS,
)

agent = agents.Agent(
    model=MODEL,
    name="groundwork-planner",
    description=("Plans a new site-suitability use case in Groundwork (data layers, scoring profile, 3D model, "
                 "Azure ML feasibility model) and drives the map; delegates to the Data Aggregator without Azure."),
    instructions=PLANNER_INSTRUCTIONS,
    temperature=0.2,
    tools=[*AGGREGATOR_TOOLS, azure_status, train_model],  # = check_parity.PLANNER_TOOLS
    subagents=[aggregator],
)
