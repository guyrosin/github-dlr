import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import emoji
from alive_progress import alive_bar
from dotenv import load_dotenv

from github_dlr.loader import start_loading_animation, stop_loading_animation

GITHUB_ACCESS_TOKEN_KEY = "GITHUB_ACCESS_TOKEN"

load_dotenv()


def printx(input):
    """Print with emoji support."""
    return print(emoji.emojize(input))


def normalize_github_url(github_url: str):
    """Normalize the provided Github directory path into a dict."""

    github_url = github_url.strip()
    if not github_url.lower().startswith("https://github.com/"):
        raise ValueError("Not a valid Github URL")

    parsed_url = urlparse(github_url)
    github_path = parsed_url.path.split("/")
    owner = github_path[1]
    repo = github_path[2]
    branch = github_path[4]
    target = github_path[-1]
    target_path = "/".join(github_path[5:-1])
    return {
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "target": target,
        "target_path": target_path,
    }


async def get_contents(content_url, *, ignore_extensions: list[str] | None = None):
    """Extract all contents of given content url and return a 1D array."""

    download_urls = []

    headers = {}
    if access_token := os.getenv(GITHUB_ACCESS_TOKEN_KEY):
        headers["Authorization"] = f"Bearer {access_token}"

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(content_url) as response:
            if response.ok:
                response = await response.json()
                if isinstance(response, dict):
                    # If the response is dict it indicates it's a single file URL
                    # in this case, return a dict only to handle it early below.
                    return {
                        "name": response.get("name"),
                        "download_url": response.get("download_url"),
                        "content_blob": response.get("content"),
                    }
                for resp in response:
                    content_name = resp.get("name")
                    content_type = resp.get("type")
                    content_self_url = resp.get("url")
                    content_download_url = resp.get("download_url")
                    if content_type == "dir":
                        sub_content = await get_contents(content_self_url)
                        for sub_item in sub_content:
                            sub_item["name"] = (
                                f"{content_name}/{sub_item.get('name', '')}"
                            )
                            download_urls.append(sub_item)
                    elif content_type == "file":
                        if ignore_extensions:
                            if any(
                                content_name.endswith(ext) for ext in ignore_extensions
                            ):
                                continue
                        download_urls.append(
                            {"name": content_name, "download_url": content_download_url}
                        )
            else:
                download_urls.append(
                    {"download_url": content_url, "response": response}
                )
    return download_urls


async def download_content(download_url, output_file):
    """Download a single downloadable file given a download URL."""

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                response.raise_for_status()
                resp_content = await response.read()

                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, mode="wb") as file:
                    file.write(resp_content)
    except BaseException:
        printx(f":warning: Failed to download {download_url!r}. Skipping this file!")


async def download_with_progress(download_url, content_filename, bar):
    # This async task is for only to show the Alive bar progress
    # on each download completion. Without wrapping these two pieces
    # of code together in an async func, it is hard to show the visual
    # progress bar per download. This is not needed for synchronous
    # downloads. Since we are using async programming, it offer a better
    # visual output.
    await download_content(download_url, content_filename)
    bar()


async def main(
    github_url, output_dir: str = "", *, ignore_extensions: list[str] | None = None
):
    """Main function."""

    repo_data = normalize_github_url(github_url)
    owner = repo_data.get("owner")
    repo = repo_data.get("repo")
    branch = repo_data.get("branch")
    root_target = repo_data.get("target")
    root_target_path = os.path.join(output_dir, root_target)

    if target_path := repo_data.get("target_path"):
        target_path = target_path + "/" + root_target
    else:
        target_path = root_target
    content_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{target_path}?ref={branch}"

    # Start the loading animation in a separate thread
    # Start the loading animation with a custom message
    loading_thread = start_loading_animation(
        "Extracting the repository content information"
    )
    contents = await get_contents(content_url, ignore_extensions=ignore_extensions)
    # Stop the loading animation
    stop_loading_animation(loading_thread)

    is_single_file = isinstance(contents, dict)
    if is_single_file:
        await download_content(contents.get("download_url"), root_target_path)
        output_str = f"\n:package: Downloaded {root_target!r} file from repo {repo!r} "
        output_str += (
            "to current directory." if output_dir == "" else f"to {output_dir!r}."
        )
        printx(output_str)
        return

    # Create the target directory first.
    os.makedirs(root_target_path, exist_ok=True)

    download_tasks = []

    with alive_bar(len(contents), stats=None) as bar:
        for content in contents:
            content_path = content.get("name")
            download_url = content.get("download_url")

            if download_url is None:
                continue
            if content_path is None:
                if response := content.get("response"):
                    printx(
                        f":warning: Failed to fetch content from {content_url!r}: {response.status} {response.reason}"
                    )
                continue

            # Extract the parent directory path and file from the current
            # 'content_path' and properly join with root target directory.
            content_parentdir = os.path.dirname(content_path)
            content_parentdir = os.path.join(root_target_path, content_parentdir)
            content_filename = os.path.join(root_target_path, content_path)

            os.makedirs(content_parentdir, exist_ok=True)

            # Update the progress bar with the name of the file being downloaded
            bar.text(f"Downloading {content_path}")

            task = asyncio.create_task(
                download_with_progress(download_url, content_filename, bar)
            )
            download_tasks.append(task)

        await asyncio.gather(*download_tasks)

    try:
        Path(root_target_path).rmdir()
        printx(f":warning: No content found in {content_url!r}.")
        return
    except OSError:
        pass
    output_str = f"\n:package: Downloaded {root_target!r} folder from repo {repo!r} "
    output_str += "to current directory." if output_dir == "" else f"to {output_dir!r}."
    printx(output_str)
