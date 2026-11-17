"""Resilient HTTP client with retry logic, HTML-404 guard, and concurrent execution."""

from __future__ import annotations

import json
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

try:
    import urllib3
except ImportError:  # pragma: no cover - optional speedup when urllib3 is present
    urllib3 = None  # type: ignore[assignment]

from .base import CategoryResult, DownloadTask

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class HttpError404(Exception):
    """Raised when resource returns 404 or SPA HTML fallback."""


_POOL_LOCK = threading.Lock()
_DIRECT_POOL: Any = None
_PROXY_POOLS: dict[str, Any] = {}


def _get_urllib3_pool(url: str) -> Any:
    if urllib3 is None:
        return None
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    scheme = parsed.scheme.lower() or "https"
    proxies = urllib.request.getproxies()
    proxy_url = None
    if not (host and urllib.request.proxy_bypass(host)):
        proxy_url = proxies.get(scheme) or proxies.get("https") or proxies.get("http")

    ca_file = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE") or ssl.get_default_verify_paths().cafile
    with _POOL_LOCK:
        if proxy_url:
            pool = _PROXY_POOLS.get(proxy_url)
            if pool is None:
                pool = urllib3.ProxyManager(
                    proxy_url,
                    num_pools=16,
                    maxsize=32,
                    ca_certs=ca_file,
                    cert_reqs="CERT_REQUIRED",
                )
                _PROXY_POOLS[proxy_url] = pool
            return pool
        global _DIRECT_POOL
        if _DIRECT_POOL is None:
            _DIRECT_POOL = urllib3.PoolManager(
                num_pools=16,
                maxsize=32,
                ca_certs=ca_file,
                cert_reqs="CERT_REQUIRED",
            )
        return _DIRECT_POOL


def fetch_bytes(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 60,
    retries: int = 4,
    reject_html: bool = False,
) -> bytes:
    req_headers = {"User-Agent": DEFAULT_UA}
    if headers:
        req_headers.update(headers)

    pool = _get_urllib3_pool(url)
    retry_cfg = (
        urllib3.Retry(total=5, connect=0, read=0, redirect=5, status=0, other=0)
        if pool is not None and urllib3 is not None
        else None
    )

    last_err: Exception | None = None
    for attempt in range(retries):
        throttled = False
        try:
            if pool is not None:
                resp = pool.request(
                    "GET",
                    url,
                    headers=req_headers,
                    timeout=timeout,
                    retries=retry_cfg,
                )
                if resp.status in (404, 410):
                    raise HttpError404(f"HTTP {resp.status}: {url}")
                if resp.status >= 400:
                    throttled = resp.status in (429, 502, 503, 504)
                    last_err = RuntimeError(f"HTTP {resp.status}: {url}")
                else:
                    ct = (resp.headers.get("Content-Type") or "").lower()
                    data = resp.data
                    if reject_html and "text/html" in ct:
                        raise HttpError404(f"HTML fallback page returned for {url}")
                    return data
            else:
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
            throttled = e.code in (429, 502, 503, 504)
            last_err = e
        except HttpError404:
            raise
        except Exception as e:
            last_err = e
        if attempt < retries - 1:
            wait_sec = min(12.0, 1.5 * (2**attempt)) if throttled else (0.75 * (attempt + 1))
            time.sleep(wait_sec)

    assert last_err is not None
    raise last_err


def fetch_json(
    url: str,
    headers: Optional[dict[str, str]] = None,
    timeout: int = 60,
    retries: int = 4,
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


def download_one(
    task: DownloadTask,
    timeout: int = 60,
    retries: int = 4,
    request_delay: float = 0.0,
) -> tuple[str, str]:
    """
    Returns status tuple:
      ("skipped", "") | ("downloaded", "") | ("missing", msg) | ("failed", msg)
    """
    if task.dest.exists() and task.dest.stat().st_size > 0:
        return "skipped", ""

    if request_delay > 0:
        time.sleep(request_delay)

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


def _load_404_cache(cache_404_path: Optional[Path]) -> set[str]:
    if not cache_404_path or not cache_404_path.exists():
        return set()
    try:
        data = json.loads(cache_404_path.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except Exception:
        return set()


def _save_404_cache(cache_404_path: Optional[Path], urls: set[str]) -> None:
    if not cache_404_path:
        return
    cache_404_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_404_path.with_name(cache_404_path.name + ".tmp")
    tmp.write_text(json.dumps(sorted(urls)), encoding="utf-8")
    tmp.replace(cache_404_path)


def run_download_tasks(
    tasks: Iterable[DownloadTask],
    game: str,
    category: str,
    output_path: Path,
    threads: int = 8,
    note: str = "",
    request_delay: float = 0.0,
    cache_404_path: Optional[Path] = None,
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

    known_404 = _load_404_cache(cache_404_path)
    pending: list[DownloadTask] = []
    cached_404_hits = 0
    for t in task_list:
        if t.dest.exists() and t.dest.stat().st_size > 0:
            result.skipped += 1
        elif t.optional and t.url in known_404:
            result.total = max(0, result.total - 1)
            cached_404_hits += 1
        else:
            pending.append(t)

    if not pending:
        print(
            f"[{game}:{category}] All {len(task_list)} tasks already resolved "
            f"(skip={result.skipped}, cached_404={cached_404_hits})."
        )
        return result

    print(
        f"[{game}:{category}] Starting {len(pending)} HTTP tasks "
        f"(total={len(task_list)}, skip={result.skipped}, cached_404={cached_404_hits}, threads={threads})..."
    )
    lock = threading.Lock()
    done = 0
    step = max(1, min(50, len(pending) // 10 or 1))
    last_flush = time.time()
    cache_dirty = False

    with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
        futures = {
            pool.submit(download_one, t, 60, 4, request_delay): t
            for t in pending
        }
        for fut in as_completed(futures):
            task = futures[fut]
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
                    if cache_404_path and msg.startswith(("HTTP 404", "HTTP 410", "HTML fallback")):
                        known_404.add(task.url)
                        cache_dirty = True
                else:
                    result.failed += 1
                    if len(result.errors) < 10:
                        result.errors.append(msg)

                now = time.time()
                if cache_dirty and cache_404_path and (now - last_flush >= 15.0):
                    _save_404_cache(cache_404_path, known_404)
                    cache_dirty = False
                    last_flush = now

                if done % step == 0 or done == len(pending):
                    print(
                        f"[{game}:{category}] Progress {done}/{len(pending)} "
                        f"(ok={result.downloaded}, skip={result.skipped}, fail={result.failed})"
                    )

    if cache_dirty and cache_404_path:
        _save_404_cache(cache_404_path, known_404)
    return result
