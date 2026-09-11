from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from heatstress import live  # noqa: E402

# In-memory cache for the live forecast. Rebound in a single assignment, so a
# request sees either the whole old payload or the whole new one -- unlike the
# seven files on disk, which are seven separate swaps.
live_cache = None


async def refresh_forecast_loop():
    """Recompute and republish the live forecast on an interval.

    Shares `refresh_once` with scripts/08_live_scheduler.py, which takes a lock:
    if the scheduler is also running, exactly one of us computes per cycle and
    the other reads what it wrote. Writing (rather than only caching in memory)
    keeps `web/data/live/` current for the disk-fallback routes below and for
    the static build.
    """
    global live_cache
    interval = live.LIVE_REFRESH_SECONDS
    while True:
        try:
            result = await asyncio.to_thread(
                live.refresh_once, live.DEFAULT_CONFIG,
                freshness_floor=min(interval / 2, 60.0),
            )
            live_cache = result.payload
            print(f"[live] {result.status} in {result.duration_s:.1f}s · "
                  f"generated {result.payload['meta']['generated_at_ist']}")
        except Exception as e:
            # Never let the loop die: the previous payload stays served.
            print(f"[live] refresh failed, serving last good: {e!r}")
        await asyncio.sleep(interval)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the background task
    task = asyncio.create_task(refresh_forecast_loop())
    yield
    # Cancel the task on shutdown
    task.cancel()

app = FastAPI(title="HeatLens API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# HEALTH
# --------------------------------------------------------------------------

def _city_name() -> str:
    """City is config-driven (NFR-5), so the badge must not hardcode Ahmedabad."""
    try:
        import yaml
        cfg = yaml.safe_load((ROOT / live.DEFAULT_CONFIG).read_text(encoding="utf-8"))
        return (cfg.get("city") or {}).get("name", "unknown")
    except Exception:
        return "unknown"


@app.get("/")
@app.get("/api/health")
def health():
    """Liveness probe the frontend polls before it fetches a dataset.

    `live_refreshed_at` separates "API up, still serving the baked floor" from
    "API up and recomputing" -- which is the distinction the status badge in the
    UI is actually claiming, and the one that was invisible before.
    """
    return {
        "status": "ok",
        # One product name (D18). This line survived the rename pass because it
        # is a string in a health payload rather than anything the UI renders.
        "server": "HeatLens Thermal Intelligence API",
        "version": app.version,
        "city": _city_name(),
        "live_refreshed_at": (
            live_cache["meta"]["generated_at_ist"] if live_cache else None
        ),
    }


DATA_DIR = Path(__file__).parent.parent / "web" / "data"
LIVE_DIR = DATA_DIR / "live"

def get_data_dir(is_live: bool = False) -> Path:
    return LIVE_DIR if is_live else DATA_DIR

def load_json(filename: str, is_live: bool = False):
    """Read a baked file, tolerating a refresher swapping it underneath us.

    A refresh replaces these files atomically, but on Windows the replace can
    briefly make the name unopenable. Retrying distinguishes "being replaced
    right now" from "never existed", so a race returns data rather than a 404.
    """
    file_path = get_data_dir(is_live) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Data file not found: {filename}")
    try:
        return live.read_json_retry(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Data file not found: {filename}")

# --------------------------------------------------------------------------
# UNIFIED FRONTEND API ENDPOINTS (/api/health, /api/heat-data)
# --------------------------------------------------------------------------

@app.get("/api/health")
def get_health():
    return {
        "status": "ok",
        "server": "HeatLens Thermal Intelligence API",
        "version": "1.0.0",
        "city": "Ahmedabad",
        "mode": "live" if live_cache else "historical",
    }

@app.get("/api/heat-data")
def get_heat_data(dataset: str = "live"):
    is_live = dataset == "live"
    if is_live and live_cache:
        return {
            "meta": live_cache["meta"],
            "hexes": live_cache["map"],
            "hourly": live_cache["hourly"],
            "city": live_cache["summary"],
            "personas": live_cache["personas"],
            "advisory": live_cache["advisory"],
            "insights": live_cache["insights"],
        }
    return {
        "meta": load_json("meta.json", is_live=is_live),
        "hexes": load_json("hexes.geojson", is_live=is_live),
        "hourly": load_json("hourly.json", is_live=is_live),
        "city": load_json("city.json", is_live=is_live),
        "personas": load_json("personas.json", is_live=is_live),
        "advisory": load_json("advisory.json", is_live=is_live),
        "insights": load_json("insights.json", is_live=is_live),
    }

# --------------------------------------------------------------------------
# HISTORICAL ENDPOINTS (May 2010 Hindcast)
# --------------------------------------------------------------------------

@app.get("/api/v1/historical/map")
def get_historical_map():
    return load_json("hexes.geojson", is_live=False)

@app.get("/api/v1/historical/summary")
def get_historical_summary():
    return load_json("city.json", is_live=False)

@app.get("/api/v1/historical/hourly")
def get_historical_hourly():
    return load_json("hourly.json", is_live=False)

@app.get("/api/v1/historical/cell/{hex_id}")
def get_historical_cell(hex_id: str):
    hourly = load_json("hourly.json", is_live=False)
    if hex_id not in hourly["hexes"]:
        raise HTTPException(status_code=404, detail="Hex ID not found")
    return {
        "meta": hourly["meta"],
        "data": hourly["hexes"][hex_id]
    }

@app.get("/api/v1/historical/personas")
def get_historical_personas():
    return load_json("personas.json", is_live=False)

@app.get("/api/v1/historical/advisory")
def get_historical_advisory():
    return load_json("advisory.json", is_live=False)

@app.get("/api/v1/historical/insights")
def get_historical_insights():
    return load_json("insights.json", is_live=False)

@app.get("/api/v1/historical/meta")
def get_historical_meta():
    return load_json("meta.json", is_live=False)


# --------------------------------------------------------------------------
# FORECAST ENDPOINTS (Live Mode)
# --------------------------------------------------------------------------

@app.get("/api/v1/forecast/map")
@app.get("/api/v1/live/map")
def get_forecast_map():
    if live_cache: return live_cache["map"]
    return load_json("hexes.geojson", is_live=True)

@app.get("/api/v1/forecast/summary")
@app.get("/api/v1/live/summary")
def get_forecast_summary():
    if live_cache: return live_cache["summary"]
    return load_json("city.json", is_live=True)

@app.get("/api/v1/forecast/hourly")
@app.get("/api/v1/live/hourly")
def get_forecast_hourly():
    if live_cache: return live_cache["hourly"]
    return load_json("hourly.json", is_live=True)

@app.get("/api/v1/forecast/cell/{hex_id}")
@app.get("/api/v1/live/cell/{hex_id}")
def get_forecast_cell(hex_id: str):
    hourly = live_cache["hourly"] if live_cache else load_json("hourly.json", is_live=True)
    if hex_id not in hourly["hexes"]:
        raise HTTPException(status_code=404, detail="Hex ID not found")
    return {
        "meta": hourly["meta"],
        "data": hourly["hexes"][hex_id]
    }

@app.get("/api/v1/forecast/personas")
@app.get("/api/v1/live/personas")
def get_forecast_personas():
    if live_cache: return live_cache["personas"]
    return load_json("personas.json", is_live=True)

@app.get("/api/v1/forecast/advisory")
@app.get("/api/v1/live/advisory")
def get_forecast_advisory():
    if live_cache: return live_cache["advisory"]
    return load_json("advisory.json", is_live=True)

@app.get("/api/v1/forecast/insights")
@app.get("/api/v1/live/insights")
def get_forecast_insights():
    if live_cache: return live_cache["insights"]
    return load_json("insights.json", is_live=True)

@app.get("/api/v1/forecast/meta")
@app.get("/api/v1/live/meta")
def get_forecast_meta():
    if live_cache: return live_cache["meta"]
    return load_json("meta.json", is_live=True)

