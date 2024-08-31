import os
from urllib.parse import urlparse

import emoji
import requests
from alive_progress import alive_bar

# Modified print to support emoji syntax
printx = lambda input: print(emoji.emojize(input))


def normalize_github_url(github_url):
    """Normalize the provided Github directory path into a dict."""

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


def get_contents(content_url):
    """Extract all contents of given content url and return a 1D array."""

    response = requests.get(content_url)
    download_urls = []
    if response.ok:
        response = response.json()
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
                sub_content = get_contents(content_self_url)
                for sub_item in sub_content:
                    sub_item["name"] = f"{content_name}/{sub_item.get('name')}"
                    download_urls.append(sub_item)
            elif content_type == "file":
                download_urls.append(
                    {"name": content_name, "download_url": content_download_url}
                )
        return download_urls


def download_content(download_url, output_file):
    """Download a single downloadable file given a download URL."""

    resp = requests.get(download_url)
    resp_content = resp.content

    with open(output_file, mode="wb") as file:
        file.write(resp_content)


def main(github_url, output_dir=None):
    """Main function."""

    repo_data = normalize_github_url(github_url)
    owner = repo_data.get("owner")
    repo = repo_data.get("repo")
    branch = repo_data.get("branch")
    root_target = repo_data.get("target")
    root_target_path = os.path.join(output_dir, root_target)

    target_path = repo_data.get("target_path") + "/" + root_target
    content_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{target_path}?ref={branch}"
    contents = get_contents(content_url)

    is_single_file = isinstance(contents, dict)
    if is_single_file:
        download_content(contents.get("download_url"), root_target_path)
        printx(f"\n:package: Downloaded {root_target!r} file from repo {repo!r}.")
        return

    # Create the target directory first.
    os.makedirs(root_target_path, exist_ok=True)

    with alive_bar(len(contents)) as bar:
        for content in contents:
            content_path = content.get("name")
            download_url = content.get("download_url")

            if download_url is None:
                continue

            # Extract the parent directory path and file from the current
            # 'content_path' and properly join with root target directory.
            content_parentdir = os.path.dirname(content_path)
            content_parentdir = os.path.join(root_target_path, content_parentdir)
            content_filename = os.path.join(root_target_path, content_path)

            os.makedirs(content_parentdir, exist_ok=True)

            download_content(download_url, content_filename)

            bar()  # Update the progress bar

    output_str = f"\n:package: Downloaded {root_target!r} folder from repo {repo!r} "
    if output_dir != "":
        output_str += f"to {output_dir!r}."
    else:
        output_str += "to current directory."
    printx(output_str)
