import httpx
from pydantic import BaseModel, Field

from app.tools.plugin import ToolContext, ToolPlugin


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
        latitude = kwargs["latitude"]
        longitude = kwargs["longitude"]
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,wind_speed_10m"
            "&hourly=temperature_2m"
        )
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
        return f"open-meteo {resp.status_code}\n{resp.text}"
