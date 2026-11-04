import logging
import argparse
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

import random

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
NUM_THREADS = 5

_thread_local = threading.local()


def get_session():
  # requests.Session is not guaranteed to be thread-safe, so each thread gets its own.
  if not hasattr(_thread_local, "session"):
    _thread_local.session = requests.Session()
  return _thread_local.session


def download_mappings(version_id, metadata_url, target):
  session = get_session()

  logging.debug(f"Downloading metadata for {version_id}")
  metadata = session.get(metadata_url).json()

  logging.info(f"Downloading mappings for {version_id}")
  mappings_url = metadata["downloads"]["client_mappings"]["url"]
  response = session.get(mappings_url, stream=True)
  response.raise_for_status()

  with open(os.path.join(target, f"{version_id}.txt"), "wb") as mappings_out:
    for chunk in response.iter_content(chunk_size=1 << 16):
      mappings_out.write(chunk)

def main():
  logging.basicConfig(level=logging.INFO)

  logging.debug("Checking info")
  parser = argparse.ArgumentParser()
  parser.add_argument("target", type=str, help="Destination directory for Mojmap documents")
  parser.add_argument("-i", "--download_versions", type=str, required=True, help="Text file with versions to include")
  args = parser.parse_args()

  if not os.path.isdir(args.target):
    raise FileNotFoundError(args.target)

  session = requests.Session()

  logging.debug("Getting version metadata URLs")
  version_manifest = session.get(VERSION_MANIFEST_URL).json()
  urls_by_id = {version["id"]: version["url"] for version in version_manifest["versions"]}

  with open(args.download_versions) as download_versions:
    ids = [line.strip() for line in download_versions if line.strip()]

  random.Random(67).shuffle(ids)

  missing = [version_id for version_id in ids if version_id not in urls_by_id]
  if missing:
    raise ValueError(f"Unknown versions: {', '.join(missing)}")

  with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
    futures = [
      executor.submit(download_mappings, version_id, urls_by_id[version_id], args.target)
      for version_id in ids
    ]
    # Calling result() re-raises any exception raised in a worker thread.
    for future in futures:
      future.result()


if __name__ == "__main__":
  main()
