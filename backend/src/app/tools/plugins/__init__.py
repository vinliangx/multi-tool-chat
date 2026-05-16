"""Consolidated plugin registry."""

from app.tools.plugin import ToolPlugin
from app.tools.plugins.http_fetch import HttpFetchPlugin
from app.tools.plugins.csv_s3 import CsvS3Plugin
from app.tools.plugins.image_s3 import ImageS3Plugin
from app.tools.plugins.sql_query import SqlQueryPlugin
from app.tools.plugins.sql_ddl import SqlDdlPlugin
from app.tools.plugins.sql_dml import SqlDmlPlugin
from app.tools.plugins.weather_api import WeatherPlugin
from app.tools.plugins.recall import RecallPlugin
from app.tools.plugins.save_memory import SaveMemoryPlugin
from app.tools.plugins.read_memory import ReadMemoryPlugin

ALL_PLUGINS: list[ToolPlugin] = [
    HttpFetchPlugin(),
    CsvS3Plugin(),
    ImageS3Plugin(),
    SqlQueryPlugin(),
    SqlDdlPlugin(),
    SqlDmlPlugin(),
    WeatherPlugin(),
    RecallPlugin(),
    SaveMemoryPlugin(),
    ReadMemoryPlugin(),
]
