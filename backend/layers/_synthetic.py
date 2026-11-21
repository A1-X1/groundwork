"""Deterministic synthetic fields shaped like London, used when a real source fails.

Everything is seeded from the layer id (CRC32), so the same grid always produces the
same values. Patterns are plausible, not real: urban heat island around the centre,
low ground along the Thames, deprivation weighted to the east, prices to the west.
"""

from __future__ import annotations

import zlib
from functools import lru_cache

import numpy as np
import pandas as pd

from . import _places
from ._geo import CENTRE_LAT, CENTRE_LON, THAMES, densify, grid_xy, nearest_distance, points_xy, to_xy


def rng(name: str) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(name.encode()))


def gaussian(grid: pd.DataFrame, lon: float, lat: float, sigma_m: float) -> np.ndarray:
    xy = grid_xy(grid)
    c = to_xy([lat], [lon])[0]
    d2 = ((xy - c) ** 2).sum(axis=1)
    return np.exp(-d2 / (2 * sigma_m**2))


def smooth_noise(grid: pd.DataFrame, name: str, n_bumps: int = 60, scale_m: float = 3500) -> np.ndarray:
    """Spatially smooth noise, mean ~0 and std ~1, from random Gaussian bumps."""
    r = rng("noise:" + name)
    xy = grid_xy(grid)
    lo, hi = xy.min(axis=0) - 2000, xy.max(axis=0) + 2000
    centres = r.uniform(lo, hi, size=(n_bumps, 2))
    amps = r.normal(0, 1, size=n_bumps)
    sig = scale_m * r.uniform(0.6, 1.4, size=n_bumps)
    d2 = ((xy[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
    field = (amps * np.exp(-d2 / (2 * sig**2))).sum(axis=1)
    std = field.std()
    return (field - field.mean()) / (std if std > 0 else 1.0)


def dist_centre_m(grid: pd.DataFrame) -> np.ndarray:
    return np.linalg.norm(grid_xy(grid) - to_xy([CENTRE_LAT], [CENTRE_LON])[0], axis=1)


def dist_thames_m(grid: pd.DataFrame) -> np.ndarray:
    return nearest_distance(grid, densify(THAMES, 100)).to_numpy()


def uhi(grid: pd.DataFrame) -> np.ndarray:
    """Urban heat island intensity, 1 at the centre fading to ~0 at the edge."""
    return np.exp(-((dist_centre_m(grid) / 9000) ** 2))


def east_west(grid: pd.DataFrame) -> np.ndarray:
    """-1 at the western edge, +1 at the eastern edge."""
    x = grid_xy(grid)[:, 0]
    return np.clip(x / 25_000, -1, 1)


def elevation(grid: pd.DataFrame) -> np.ndarray:
    """Metres above sea level: Thames floodplain low, northern heights and Downs high."""
    thames_km = dist_thames_m(grid) / 1000
    z = 5 + 28 * (1 - np.exp(-thames_km / 4))
    for lon, lat, h, s in [(-0.165, 51.565, 95, 2500),   # Hampstead / Highgate
                           (-0.070, 51.420, 75, 2200),   # Crystal Palace / Sydenham Hill
                           (0.030, 51.305, 170, 6000),   # North Downs (Biggin Hill)
                           (-0.140, 51.300, 120, 4000),  # Coulsdon / Farthing Downs
                           (-0.335, 51.600, 75, 3500),   # Harrow on the Hill / Stanmore
                           (-0.200, 51.650, 80, 4000),   # Barnet plateau
                           (0.200, 51.610, 60, 4000),    # Havering ridge
                           (0.000, 51.450, 35, 3000)]:   # Shooters Hill / Blackheath
        z += h * gaussian(grid, lon, lat, s)
    z += 4 * smooth_noise(grid, "elevation", 120, 1500)
    return np.maximum(z, 0.5)


def population_density(grid: pd.DataFrame) -> np.ndarray:
    """Residents per km²: dense inner ring, low-residential core, sparse green fringe."""
    d_km = dist_centre_m(grid) / 1000
    dens = 2200 + 10_500 * np.exp(-(((d_km - 6) / 7) ** 2))
    dens *= 1 - 0.65 * np.exp(-((d_km / 1.8) ** 2))  # the City / West End
    dens *= np.exp(0.22 * smooth_noise(grid, "population", 150, 1500))
    dens *= 1 - 0.75 * np.clip((d_km - 18) / 6, 0, 1)  # green belt fringe
    for _, lon, lat, r in _places.PROTECTED_SITES:
        dens *= 1 - 0.85 * gaussian(grid, lon, lat, r)
    dens *= 1 - 0.9 * gaussian(grid, *_places.HEATHROW, 1500)
    return np.maximum(dens, 30)


def sample_points(grid: pd.DataFrame, name: str, n: int, weight: np.ndarray,
                  jitter_m: float = 350) -> list[tuple[float, float]]:
    """``n`` (lon, lat) points: hexes drawn ∝ weight, then jittered."""
    r = rng("points:" + name)
    p = np.clip(np.asarray(weight, dtype=float), 0, None)
    p = p / p.sum()
    idx = r.choice(len(grid), size=n, p=p, replace=True)
    lat = grid["lat"].to_numpy()[idx] + r.normal(0, jitter_m / 111_320, n)
    lon = grid["lon"].to_numpy()[idx] + r.normal(0, jitter_m / 69_400, n)
    return list(zip(lon.tolist(), lat.tolist(), strict=True))


@lru_cache(maxsize=8)
def _radial_roads() -> tuple[tuple[tuple[float, float], ...], ...]:
    r = rng("roads")
    lines = []
    for angle in np.linspace(0, 2 * np.pi, 14, endpoint=False):
        a = angle + r.normal(0, 0.06)
        pts = []
        for k, dist in enumerate(np.linspace(500, 32_000, 40)):
            wiggle = 400 * np.sin(k / 3 + angle * 5)
            x = dist * np.cos(a) - wiggle * np.sin(a)
            y = dist * np.sin(a) + wiggle * np.cos(a)
            pts.append((CENTRE_LON + x / 69_400, CENTRE_LAT + y / 111_320))
        lines.append(tuple(pts))
    for rx, ry, start, stop in [(11_500, 8_500, 0, np.pi),        # North Circular
                                (8_500, 6_500, np.pi, 2 * np.pi),  # South Circular
                                (27_000, 23_000, 0, 2 * np.pi)]:   # M25 (mostly outside)
        t = np.linspace(start, stop, 120)
        lines.append(tuple((CENTRE_LON + rx * np.cos(v) / 69_400,
                            CENTRE_LAT + ry * np.sin(v) / 111_320) for v in t))
    return tuple(lines)


def major_roads() -> list[list[tuple[float, float]]]:
    return [list(line) for line in _radial_roads()]


def hv_lines() -> list[list[tuple[float, float]]]:
    """Plausible 275/400 kV corridors into London (lon, lat)."""
    return [
        [(-0.020, 51.720), (-0.030, 51.640), (-0.025, 51.580), (-0.010, 51.530)],  # Lee Valley
        [(-0.520, 51.530), (-0.420, 51.520), (-0.330, 51.515), (-0.270, 51.520)],  # Iver → Park Royal
        [(0.330, 51.480), (0.200, 51.500), (0.100, 51.510), (0.020, 51.515)],      # Thames estuary
        [(-0.160, 51.280), (-0.140, 51.360), (-0.110, 51.420)],                    # Croydon south
        [(-0.330, 51.690), (-0.290, 51.620), (-0.250, 51.570)],                    # Elstree
        [(0.180, 51.420), (0.120, 51.450), (0.060, 51.470)],                       # Kent → Greenwich
    ]


def water_points(grid: pd.DataFrame) -> np.ndarray:
    """Thames + reservoirs + a few tributaries, as projected xy points."""
    tributaries = [
        [(-0.020, 51.700), (-0.030, 51.620), (-0.020, 51.560), (-0.005, 51.510)],  # Lea
        [(-0.310, 51.580), (-0.290, 51.530), (-0.300, 51.490)],                     # Brent
        [(-0.190, 51.420), (-0.190, 51.460)],                                       # Wandle
        [(0.150, 51.620), (0.140, 51.550), (0.130, 51.515)],                        # Roding
    ]
    pts = [densify(THAMES, 50)] + [densify(t, 50) for t in tributaries]
    pts.append(points_xy([(lon, lat) for _, lon, lat in _places.RESERVOIRS]))
    return np.vstack(pts)
