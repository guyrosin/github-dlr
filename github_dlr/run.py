import asyncio

from github_dlr.source import main


def download(
    github_path: str,
    output_dir: str = "",
    *,
    ignore_extensions: list[str] | None = None,
):
    asyncio.run(main(github_path, output_dir, ignore_extensions=ignore_extensions))
