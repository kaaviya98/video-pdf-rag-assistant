import mimetypes
import tempfile
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import requests
from django.conf import settings

from app.utils.http import close_http_response


def _get_filename_from_url(url: str) -> str:
    parsed_url = urlparse(url)
    return Path(parsed_url.path).name or "downloaded_file.pdf"


def _create_dir_if_not_exists(dir_path: str) -> None:
    path = Path(dir_path)
    if not path.exists():
        path.mkdir(parents=True)


def _get_unique_path(dir_path: str, filename: str) -> str:
    base_path = Path(dir_path) / filename
    if not base_path.exists():
        return str(base_path)

    counter = 1
    while True:
        stem = base_path.stem
        suffix = base_path.suffix
        unique_path = base_path.parent / f"{stem}_{counter}{suffix}"
        if not unique_path.exists():
            return str(unique_path)
        counter += 1


def download_file(
    url: str,
    secret_token: str | None = None,
    local_dir: str | None = None,
    *,
    use_settings_secret: bool = False,
    timeout: int = 10,
    extra_headers: Mapping[str, str] | None = None,
    stream: bool = True,
    chunk_size: int = 8192,
    allow_redirects: bool = True,
) -> str:
    filename = _get_filename_from_url(url)
    target_dir = local_dir or tempfile.gettempdir()

    _create_dir_if_not_exists(target_dir)
    file_path = _get_unique_path(target_dir, filename)

    resolved_secret = secret_token
    if use_settings_secret and resolved_secret is None:
        resolved_secret = getattr(settings, "WEBHOOK_SECRET", None)

    headers: dict[str, str] = {}
    if resolved_secret:
        headers["X-Secret"] = resolved_secret
    if extra_headers:
        headers.update(extra_headers)

    response = requests.get(
        url,
        stream=stream,
        headers=headers or None,
        timeout=timeout,
        allow_redirects=allow_redirects,
    )
    try:
        response.raise_for_status()

        with Path(file_path).open("wb") as f:
            if stream:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
            else:
                f.write(response.content)

        return file_path
    finally:
        close_http_response(response)


def delete_file(file_path: str) -> None:
    path = Path(file_path)
    path.unlink(missing_ok=True)


def delete_files_in_local_dir(
    folder_path: str | Path,
    *,
    exclude_filenames: Collection[str] | None = None,
) -> None:
    folder = Path(folder_path)
    if not folder.is_dir():
        return
    skip = frozenset(exclude_filenames) if exclude_filenames else frozenset()
    for path in folder.iterdir():
        if path.is_file() and path.name not in skip:
            delete_file(str(path))


def get_storage_path(
    *,
    filename: str,
    existing_object_path: str | None = None,
) -> str:
    """Build a storage key from a folder prefix or full path provided at asset create."""
    normalized_filename = filename.lstrip("/")
    if not (existing_object_path or "").strip():
        return normalized_filename

    base = str(existing_object_path).strip().strip("/")
    if base == normalized_filename:
        return normalized_filename
    if (
        base.endswith(f"/{normalized_filename}")
        or base.split("/")[-1] == normalized_filename
    ):
        return base
    return f"{base}/{normalized_filename}"


def is_local_file(file_url: str) -> bool:
    return Path(file_url).is_file() and not file_url.startswith(("http://", "https://"))


def resolve_file_source_to_local_path(
    source: str,
    *,
    use_settings_secret: bool = False,
) -> tuple[str, bool]:
    if is_local_file(source):
        return source, False
    return download_file(source, use_settings_secret=use_settings_secret), True


def upload_folder(
    folder_path: str | Path,
    upload_url: str,
    *,
    secret: str | None = None,
    use_settings_secret: bool = True,
    public_read: bool = True,
    timeout: int = 60,
    content_type: str | None = "application/octet-stream",
    guess_mime_type: bool = False,
    extra_headers: Mapping[str, str] | None = None,
    filename_param: str = "filename",
    http_method: Literal["PUT", "POST"] = "PUT",
    multipart: bool = False,
    multipart_field: str = "file",
) -> None:
    folder = Path(folder_path)
    if not folder.is_dir():
        return

    resolved_secret = secret
    if use_settings_secret and resolved_secret is None:
        resolved_secret = getattr(settings, "WEBHOOK_SECRET", None)

    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        rel_str = rel.as_posix()

        if multipart:
            headers_mp: dict[str, str] = {}
            if resolved_secret:
                headers_mp["X-Secret"] = resolved_secret
            if extra_headers:
                headers_mp.update(extra_headers)
            with path.open("rb") as f:
                response = requests.post(
                    upload_url,
                    files={multipart_field: (rel_str, f)},
                    headers=headers_mp or None,
                    timeout=timeout,
                    allow_redirects=True,
                )
            try:
                response.raise_for_status()
            finally:
                close_http_response(response)
            continue

        target_url = _append_query_param(upload_url, filename_param, rel_str)
        resolved_ct = _content_type_for_file(
            path,
            content_type=content_type,
            guess_mime_type=guess_mime_type,
        )
        headers: dict[str, str] = {}
        if resolved_ct:
            headers["Content-Type"] = resolved_ct
        if resolved_secret:
            headers["X-Secret"] = resolved_secret
        if public_read:
            headers["x-amz-acl"] = "public-read"
        if extra_headers:
            headers.update(extra_headers)

        with path.open("rb") as f:
            request = requests.put if http_method == "PUT" else requests.post
            response = request(
                target_url,
                data=f,
                headers=headers,
                timeout=timeout,
                allow_redirects=not resolved_secret,
            )
            try:
                if resolved_secret and response.status_code in (
                    301,
                    302,
                    303,
                    307,
                    308,
                ):
                    location = response.headers.get("Location")
                    if location:
                        close_http_response(response)
                        response = None
                        f.seek(0)
                        s3_headers = {
                            k: v for k, v in headers.items() if k.lower() != "x-secret"
                        }
                        response = request(
                            location,
                            data=f,
                            headers=s3_headers or None,
                            timeout=timeout,
                            allow_redirects=True,
                        )
                if 300 <= response.status_code < 400:
                    raise requests.exceptions.HTTPError(
                        f"Unresolved redirect status {response.status_code} for URL: {response.url}",
                        response=response,
                    )
                response.raise_for_status()
            finally:
                close_http_response(response)


def _append_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    pairs = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key
    ]
    pairs.append((key, value))
    new_query = urlencode(pairs, quote_via=quote)
    return urlunparse(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            parts.params,
            new_query,
            parts.fragment,
        ),
    )


def _content_type_for_file(
    path: Path,
    *,
    content_type: str | None,
    guess_mime_type: bool,
) -> str | None:
    if guess_mime_type:
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or content_type
    return content_type
