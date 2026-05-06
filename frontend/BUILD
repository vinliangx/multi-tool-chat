files(
    name="frontend_files",
    sources=["*"]
)

docker_image(
    name="webapp",
    image_tags=["1.0","latest"],
    dependencies=[":frontend_files"]
)

