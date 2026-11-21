# Groundwork use cases

Groundwork answers one question for any kind of development: **where is the best place to build this?** It scores every hexagon of a region against a transparent, adjustable profile. Real data goes in (climate, population, hazards, infrastructure, prices), and you get a ranked map, a per-site explanation and an API.

Each audience below uses the same engine with a different profile. You can add a new building type by describing it to the Mistral agents, with no code.

---

## Business: data centres and compute-heavy infrastructure

**Who:** hyperscalers, colocation providers, AI and ML training clusters, crypto/HPC operators, investors doing site due diligence.

**What matters, and how Groundwork scores it** (the `data_centre` profile):
| Need | Layer | Why |
|---|---|---|
| Cheap cooling | `free_cooling_hours`, `wet_bulb_p99` | Hours below 18 °C let air-side economisers replace chillers. Low design wet-bulb makes evaporative cooling efficient. |
| Clean, available power | `grid_carbon_intensity`, `dist_substation`, `dist_hv_line` | Large GPU clusters need high-voltage connections and low-carbon electricity for ESG targets. |
| Connectivity | `dist_fibre_ix` (IXPs from PeeringDB) | Latency to internet exchanges and other data centres. |
| Low hazard | `flood_zone_3` (mask), `seismic_activity`, `slope` | Uptime and insurance. |
| Neighbours | `population_density`, `land_use_residential` | Noise, planning friction, land cost. |

**ML in the loop.** For profiles with a model, Groundwork trains a **presence-only LightGBM model** on where similar facilities already exist (OSM, PeeringDB). It applies the result as a *feasibility multiplier* (never above the weighted score), with **SHAP explanations** per site. With Azure ML connected, training runs as an Azure ML job in your workspace, so you can scale to larger regions and retrain as data refreshes. Without Azure, the Mistral **Data Aggregator** builds the profile from aggregated data instead.

**Typical workflow:**
1. "Find sites for a 100 MW AI training campus in the UK."
2. The planner agent adds any missing data (e.g. water access for cooling), builds the profile and trains the model.
3. Compare the shortlist with `/compare` and export the API results to your site-selection model.

---

## Consumers: homes

**Who:** home buyers and renters, relocation services, estate agents, mortgage and insurance products.

**The `house` profile weighs:** crime rate, distance to stations, good schools nearby (Ofsted), house prices (affordability), distance to primary schools, parks, NO₂, flood risk, summer heat and distance from major roads. Flood Zone 3 and protected land are excluded.

**Why it helps:** it's one map that balances commute, safety, schools, environment and price. You can move the sliders to match your priorities ("I care about schools twice as much as commute"), and every score explains itself ("crime pulls this area down by 4 points").

**Examples:**
- "Best areas to live in Manchester for a family on a budget."
- An estate-agent portal embedding the `/score/house/point` API to add a "suitability" badge to listings.
- Insurers using flood, heat and crime layers per property.

---

## Government and the public sector: hospitals, schools, public services

**Who:** local authorities, NHS trusts and health boards, education departments, transport and planning bodies.

| Profile | What it optimises |
|---|---|
| **School** | Where children live but provision is thin (`population_density` high, `dist_primary_school` far), clean air, safe streets, away from major roads, near transport and green space. Deprivation is weighted as *need*. |
| **Hospital** | Reach for the most people: dense, under-served catchments, fast road and rail access, low flood risk, clean air, a grid connection. |
| **Solar farm / Wind farm** | Renewable siting for net-zero plans: irradiance, sunshine and cloud cover, hub-height wind power density, grid connection, distance from homes and airports, protected land excluded. |
| **Custom** | Fire stations, libraries, EV charging hubs, flood defences, social housing: describe the facility and the agents build the profile. |

**Why it helps:** evidence-based, transparent siting. Weights are public and adjustable, explanations are per site, and data sources and licences are documented. It's useful for consultations ("here is why this site ranks first"), for comparing options and for spotting provision gaps.

**Responsible use:** crime and deprivation data can encode historical bias, and the ML model learns from past decisions. Groundwork is **decision support, not planning advice**. Keep the explanations visible and pair the results with local knowledge and statutory processes.

---

## Any new building: the Custom tab and Mistral agents

Describe anything ("a hydrogen refuelling station", "a vertical farm", "a 60,000-seat stadium"):
1. **The Planner agent** decides what the building needs, adds missing data layers from a vetted list of free sources (OpenStreetMap, Open-Meteo, USGS…), builds them **only for your region**, writes the profile and designs a 3D model.
2. **Training:** if Azure ML is connected, it trains the feasibility model there. If not, you're asked to connect Azure or use the **Data Aggregator** agent, which builds the profile from aggregated data and writes a plain-language note for every weight (e.g. "higher crime per 1,000 residents gives a worse score; London median ≈ 67").
3. The map opens on the new use case with the best sites highlighted and the building placed.

## Coverage

London (detailed), the United Kingdom (with finer hexes in towns and cities), the United States, Canada and Mexico. Built from free global datasets: WorldClim, WorldPop, WRI power plants, OurAirports, PeeringDB, Natural Earth, USGS and OWID. See `docs/data-sources.md` for sources, licences and which layers are real in each region.
