"""Resilient HTTP client with retry logic, HTML-404 guard, and concurrent execution."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from .base import CategoryResult, DownloadTask

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class HttpError404(Exception):
    """Raised when resource returns 404 or SPA HTML fallback."""


def fetch_bytes(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 60,
    retries: int = 3,
    reject_html: bool = False,
) -> bytes:
    req_headers = {"User-Agent": DEFAULT_UA}
    if headers:
        req_headers.update(headers)

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ct = (resp.headers.get("Content-Type") or "").lower()
                data = resp.read()
                if reject_html and "text/html" in ct:
                    raise HttpError404(f"HTML fallback page returned for {url}")
                return data
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise HttpError404(f"HTTP {e.code}: {url}") from e
            last_err = e
        except HttpError404:
            raise
        except Exception as e:
            last_err = e
        if attempt < retries - 1:
            time.sleep(0.5 * (attempt + 1))

    assert last_err is not None
    raise last_err


def fetch_json(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 60,
    retries: int = 3,
) -> Any:
    raw = fetch_bytes(
        url, headers=headers, timeout=timeout, retries=retries, reject_html=True
    )
    return json.loads(raw.decode("utf-8"))


def load_or_fetch_json(
    cache_path: Path,
    url: str,
    refresh: bool = False,
    headers: Optional[dict[str, str]] = None,
    transform: Optional[Callable[[Any], Any]] = None,
) -> Any:
    if not refresh and cache_path.exists() and cache_path.stat().st_size > 0:
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    data = fetch_json(url, headers=headers)
    if transform is not None:
        data = transform(data)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".part")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(cache_path)
    return data


def download_one(task: DownloadTask, timeout: int = 60, retries: int = 3) -> tuple[str, str]:
    """
    Returns status tuple:
      ("skipped", "") | ("downloaded", "") | ("missing", msg) | ("failed", msg)
    """
    if task.dest.exists() and task.dest.stat().st_size > 0:
        return "skipped", ""

    task.dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = task.dest.with_name(task.dest.name + ".part")
    try:
        allow_html = task.dest.suffix.lower() in (".html", ".htm")
        data = fetch_bytes(
            task.url,
            headers=task.headers,
            timeout=timeout,
            retries=retries,
            reject_html=task.reject_html and not allow_html,
        )
        if not data:
            return ("missing" if task.optional else "failed"), f"Empty response: {task.url}"
        with tmp.open("wb") as f:
            f.write(data)
        tmp.replace(task.dest)
        return "downloaded", ""
    except HttpError404 as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return ("missing" if task.optional else "failed"), str(e)
    except Exception as e:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return ("missing" if task.optional else "failed"), f"{task.url}: {e}"


def run_download_tasks(
    tasks: Iterable[DownloadTask],
    game: str,
    category: str,
    output_path: Path,
    threads: int = 8,
    note: str = "",
) -> CategoryResult:
    task_list = list(tasks)
    result = CategoryResult(
        game=game,
        category=category,
        supported=True,
        total=len(task_list),
        output_path=output_path,
        note=note,
    )
    if not task_list:
        return result

    print(f"[{game}:{category}] Starting {len(task_list)} download tasks (threads={threads})...")
    lock = threading.Lock()
    done = 0
    step = max(1, min(25, len(task_list) // 5 or 1))

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        futures = {pool.submit(download_one, t): t for t in task_list}
        for fut in as_completed(futures):
            status, msg = fut.result()
            with lock:
                done += 1
                if status == "downloaded":
                    result.downloaded += 1
                elif status == "skipped":
                    result.skipped += 1
                elif status == "missing":
                    # Optional missing variants do not count as hard errors
                    result.total = max(0, result.total - 1)
                else:
                    result.failed += 1
                    if len(result.errors) < 10:
                        result.errors.append(msg)
                if done % step == 0 or done == len(task_list):
                    print(
                        f"[{game}:{category}] Progress {done}/{len(task_list)} "
                        f"(ok={result.downloaded}, skip={result.skipped}, fail={result.failed})"
                    )
    return result
