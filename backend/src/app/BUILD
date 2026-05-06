files(
    name="app_files",
    sources=["*"],
)


python_sources()

pex_binary(
    name="api",
    entry_point="app.main:app",
    resolve="python-default",
)
