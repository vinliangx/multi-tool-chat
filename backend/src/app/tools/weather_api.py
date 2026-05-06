from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from app.tools.base import make_session_tool


class WeatherArgs(BaseModel):
    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")


async def _run(latitude: float, longitude: float) -> str:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,wind_speed_10m"
        "&hourly=temperature_2m"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url)
    return f"open-meteo {resp.status_code}\n{resp.text}"


def factory(session_id_provider):
    return make_session_tool(
        name="weather_lookup",
        description="Get current weather + hourly temperature forecast for a lat/lon via open-meteo (no key needed).",
        args_schema=WeatherArgs,
        runner=_run,
        session_id_provider=session_id_provider,
    )
