"""Loading of data files from a base URL.

Uses urllib.request, which supports https:, file: and other schemes. Use a
file:// URL for local data, e.g. --base-url file:///path/to/www/public/data

Files are expected to be gzip-compressed, but uncompressed data is accepted as
well (decided by the gzip magic bytes).
"""

import gzip
import json
import urllib.request

GZIP_MAGIC = b"\x1f\x8b"

DEFAULT_BASE_URL = "https://qikpl4.github.io/bogged/data"


def normalize_base_url(base_url: str) -> str:
    return base_url.strip().rstrip("/")


def fetch_bytes(url: str) -> bytes:
    try:
        with urllib.request.urlopen(url) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Could not fetch {url}\nHTTP {error.code} {error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not fetch {url}\n{error.reason}") from error


def gunzip_if_needed(data: bytes, url: str) -> bytes:
    if data.startswith(GZIP_MAGIC):
        try:
            return gzip.decompress(data)
        except OSError as error:
            raise RuntimeError(f"Could not decompress {url}\n{error}") from error
    return data


def load_file(base_url: str, path: str) -> bytes:
    url = f"{base_url}/{path}"
    return gunzip_if_needed(fetch_bytes(url), url)


def load_json(base_url: str, path: str):
    url = f"{base_url}/{path}"
    data = fetch_bytes(url)
    try:
        return json.loads(data)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Could not parse {url} as JSON\n{error}") from error


def index_file(side: str) -> str:
    return f"index_{side}.bin.gz"


def batch_file(chunk: int) -> str:
    return f"batch_{chunk:03d}.bin.gz"
