import asyncio

from github_dlr.source import main


def download(github_path: str, output_dir: str):
    asyncio.run(main(github_path, output_dir))
