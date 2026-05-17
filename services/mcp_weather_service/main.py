import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

mcp = FastMCP("Weather MCP Service")

_OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


@mcp.tool
async def get_weather(latitude: float, longitude: float) -> dict:
    """Get current weather and hourly temperature forecast from open-meteo."""
    url = (
        f"{_OPEN_METEO_URL}"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,wind_speed_10m"
        "&hourly=temperature_2m"
    )
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url)

    if resp.status_code != 200:
        raise ValueError(f"open-meteo error {resp.status_code}: {resp.text}")

    data = resp.json()
    current = data["current"]
    hourly = data["hourly"]

    return {
        "latitude": latitude,
        "longitude": longitude,
        "current_temperature_c": current["temperature_2m"],
        "current_wind_speed_kmh": current["wind_speed_10m"],
        "hourly_temperatures_c": hourly["temperature_2m"],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)
