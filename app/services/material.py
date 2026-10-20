"""Stock-footage service: search & download free b-roll clips.

Supports Pexels (default) and Pixabay. Both offer free HD video under licences
that allow reuse. Clips are cached on disk by URL hash.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import requests
from loguru import logger

from app.config import get_settings
from app.models import AspectRatio

_TIMEOUT = 30


def _cache_dir() -> Path:
    d = get_settings().storage_path / "cache" / "clips"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _download(url: str) -> Path:
    name = hashlib.md5(url.encode()).hexdigest() + ".mp4"
    dest = _cache_dir() / name
    if dest.exists() and dest.stat().st_size > 0:
        logger.debug(f"Clip cache hit: {dest.name}")
        return dest
    logger.info(f"Downloading clip: {url[:80]}...")
    with requests.get(url, stream=True, timeout=_TIMEOUT) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            fh.writelines(r.iter_content(chunk_size=1 << 16))
    return dest


# --------------------------------------------------------------------------- #
# Pexels
# --------------------------------------------------------------------------- #
def _pexels_search(term: str, aspect: AspectRatio, per_term: int) -> list[str]:
    cfg = get_settings().material.pexels
    if not cfg.api_key:
        raise RuntimeError("Pexels API key is not configured (set PEXELS_API_KEY or config.toml).")
    orientation = "portrait" if aspect is AspectRatio.PORTRAIT else "landscape"
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": cfg.api_key},
        params={"query": term, "orientation": orientation, "per_page": per_term, "size": "medium"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    urls: list[str] = []
    for video in resp.json().get("videos", []):
        files = sorted(
            (f for f in video.get("video_files", []) if f.get("link")),
            key=lambda f: (f.get("width") or 0),
            reverse=True,
        )
        # Pick the best HD file that isn't absurdly large.
        for f in files:
            if (f.get("width") or 0) >= 1080:
                urls.append(f["link"])
                break
        else:
            if files:
                urls.append(files[0]["link"])
    return urls


# --------------------------------------------------------------------------- #
# Pixabay
# --------------------------------------------------------------------------- #
def _pixabay_search(term: str, aspect: AspectRatio, per_term: int) -> list[str]:
    cfg = get_settings().material.pixabay
    if not cfg.api_key:
        raise RuntimeError("Pixabay API key is not configured (set PIXABAY_API_KEY or config.toml).")
    resp = requests.get(
        "https://pixabay.com/api/videos/",
        params={"key": cfg.api_key, "q": term, "per_page": max(3, per_term)},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    urls: list[str] = []
    for hit in resp.json().get("hits", []):
        videos = hit.get("videos", {})
        best = videos.get("large") or videos.get("medium") or videos.get("small")
        if best and best.get("url"):
            urls.append(best["url"])
    return urls


def _search(term: str, aspect: AspectRatio, per_term: int) -> list[str]:
    provider = get_settings().material.provider.lower()
    if provider == "pexels":
        return _pexels_search(term, aspect, per_term)
    if provider == "pixabay":
        return _pixabay_search(term, aspect, per_term)
    raise ValueError(f"Unknown material provider: {provider!r}")


def collect_clips(
    search_terms: list[str],
    aspect: AspectRatio,
    min_clips: int = 4,
    per_term: int = 2,
) -> list[Path]:
    """Search each term, download clips, return local file paths.

    Keeps going through the term list until at least ``min_clips`` are gathered
    (or terms are exhausted).
    """
    downloaded: list[Path] = []
    seen: set[str] = set()
    for term in search_terms:
        if len(downloaded) >= min_clips:
            break
        try:
            urls = _search(term, aspect, per_term)
        except requests.HTTPError as e:
            logger.warning(f"Search failed for {term!r}: {e}")
            continue
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            try:
                downloaded.append(_download(url))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Download failed ({url[:60]}...): {e}")
            if len(downloaded) >= min_clips:
                break

    if not downloaded:
        raise RuntimeError(
            "No stock clips could be downloaded. Check your material provider API key "
            "and search terms."
        )
    logger.info(f"Collected {len(downloaded)} clips")
    return downloaded
