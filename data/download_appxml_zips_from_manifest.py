#!/usr/bin/env python3
"""
Download all .zip files from a USPTO Open Data Portal manifest JSON
(same shape as data/out.txt: bulkDataProductBag -> productFileBag -> fileDataBag).

Each fileDownloadURI must be requested with header x-api-key; the server redirects
to a signed data.uspto.gov URL. Set USPTO_API_KEY in the environment.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def iter_zip_entries(manifest_path: str):
    with open(manifest_path, encoding="utf-8") as f:
        d = json.load(f)
    for product in d.get("bulkDataProductBag", []):
        for entry in (product.get("productFileBag") or {}).get("fileDataBag") or []:
            name = entry.get("fileName") or ""
            uri = entry.get("fileDownloadURI")
            if uri and name.lower().endswith(".zip"):
                yield name, uri


def download_one(url: str, dest: str, api_key: str, chunk: int = 1024 * 1024) -> None:
    req = urllib.request.Request(url, headers={"x-api-key": api_key})
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as out:
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                out.write(block)
        os.replace(tmp, dest)
    finally:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def main() -> int:
    p = argparse.ArgumentParser(description="Download APPXML zips from a manifest JSON.")
    p.add_argument(
        "manifest",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "out.txt"),
        help="Path to manifest JSON (default: data/out.txt next to this script)",
    )
    p.add_argument(
        "-o",
        "--out-dir",
        default=os.path.join(os.path.dirname(__file__), "appxml_zips"),
        help="Directory to write zips (created if missing)",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip if destination file already exists and size > 0",
    )
    args = p.parse_args()

    key = os.environ.get("USPTO_API_KEY", "").strip()
    if not key:
        print("Set USPTO_API_KEY to your USPTO Open Data Portal API key.", file=sys.stderr)
        return 1

    jobs = list(iter_zip_entries(args.manifest))
    if not jobs:
        print("No .zip entries found in manifest.", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    print(f"Found {len(jobs)} zip(s). Writing to {args.out_dir!r}")

    for i, (name, uri) in enumerate(jobs, 1):
        dest = os.path.join(args.out_dir, name)
        if args.skip_existing and os.path.isfile(dest) and os.path.getsize(dest) > 0:
            print(f"[{i}/{len(jobs)}] skip (exists): {name}")
            continue
        print(f"[{i}/{len(jobs)}] downloading {name} …")
        try:
            download_one(uri, dest, key)
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} for {name}: {e.reason}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"URL error for {name}: {e}", file=sys.stderr)
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
