import os

import httpx
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin

_WEATHER_SERVICE_URL = os.getenv("WEATHER_SERVICE_URL", "http://localhost:8002")


class WeatherArgs(BaseModel):
    latitude: float = Field(..., description="Latitude in decimal degrees")
    longitude: float = Field(..., description="Longitude in decimal degrees")


class WeatherPlugin(ToolPlugin):
    @property
    def name(self) -> str:
        return "weather_lookup"

    @property
    def description(self) -> str:
        return "Get current weather + hourly temperature forecast for a lat/lon via open-meteo (no key needed). It doesn't have to be precise."

    @property
    def args_schema(self) -> type[BaseModel]:
        return WeatherArgs

    async def execute(self, context: ToolContext, **kwargs) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_WEATHER_SERVICE_URL}/weather",
                json={"latitude": kwargs["latitude"], "longitude": kwargs["longitude"]},
            )
            resp.raise_for_status()
            data = resp.json()
        return (
            f"Current temperature: {data['current_temperature_c']}°C, "
            f"wind speed: {data['current_wind_speed_kmh']} km/h\n"
            f"Hourly temperatures (°C): {data['hourly_temperatures_c']}"
        )
