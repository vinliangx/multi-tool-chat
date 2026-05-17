import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Weather MCP Service")

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherRequest(BaseModel):
    latitude: float
    longitude: float


class WeatherResponse(BaseModel):
    latitude: float
    longitude: float
    current_temperature_c: float
    current_wind_speed_kmh: float
    hourly_temperatures_c: list[float]


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/weather", response_model=WeatherResponse)
async def get_weather(body: WeatherRequest) -> WeatherResponse:
    url = (
        f"{_OPEN_METEO_URL}"
        f"?latitude={body.latitude}&longitude={body.longitude}"
        "&current=temperature_2m,wind_speed_10m"
        "&hourly=temperature_2m"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url)

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"open-meteo error {resp.status_code}: {resp.text}")

    data = resp.json()
    current = data["current"]
    hourly = data["hourly"]

    return WeatherResponse(
        latitude=body.latitude,
        longitude=body.longitude,
        current_temperature_c=current["temperature_2m"],
        current_wind_speed_kmh=current["wind_speed_10m"],
        hourly_temperatures_c=hourly["temperature_2m"],
    )
