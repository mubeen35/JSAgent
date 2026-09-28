"""
Job fetcher that pulls from Arbeitnow and Remotive APIs.

Validates URLs before hitting them (allowlisted hosts, no private IPs,
HTTPS only). Deduplicates across sources by job_id.
"""

import ipaddress
import json
import logging
import socket
import time
from typing import Any, Dict, List, Set
from urllib.parse import urlencode, urlparse, urlunparse

import requests

from config import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
INTER_REQUEST_DELAY = 0.5

_ARBEITNOW_BASE = "https://www.arbeitnow.com/api/job-board-api"

_REMOTIVE_CATEGORIES = ["software-dev", "data"]
_REMOTIVE_BASE = "https://remotive.com/api/remote-jobs"

# don't let requests go to internal networks
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_ip(host: str) -> bool:
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in addrs:
        try:
            ip = ipaddress.ip_address(info[4][0])
            if any(ip in net for net in _BLOCKED_NETWORKS):
                return True
        except ValueError:
            return True
    return False


def _validate_url(base_url: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise ValueError(f"Only HTTPS allowed, got '{parsed.scheme}'")
    host = parsed.hostname or ""
    if host not in settings.ALLOWED_HOSTS:
        raise ValueError(f"Host '{host}' not in allowed list")
    if _is_private_ip(host):
        raise ValueError(f"Host '{host}' resolves to private IP")


def _get_json(url: str) -> Any:
    resp = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"Accept": "application/json", "User-Agent": "JobSearchAgent/2.0"},
        stream=True,
    )
    resp.raise_for_status()
    raw = resp.raw.read(MAX_RESPONSE_BYTES, decode_content=True)
    return json.loads(raw)


# --- arbeitnow ---

def _fetch_arbeitnow_page(query: str, page: int) -> List[Dict[str, Any]]:
    params: Dict[str, Any] = {"page": page}
    if query:
        params["search"] = query

    parts = urlparse(_ARBEITNOW_BASE)
    url = urlunparse(parts._replace(query=urlencode(params)))

    try:
        data = _get_json(url)
        jobs = data.get("data", [])
        if not isinstance(jobs, list):
            return []

        result = []
        for j in jobs:
            result.append({
                "job_id":        str(j.get("slug") or j.get("id") or ""),
                "title":         j.get("title", ""),
                "company":       j.get("company_name", ""),
                "location":      j.get("location", ""),
                "remote":        bool(j.get("remote", False)),
                "description":   j.get("description", ""),
                "url":           j.get("url", ""),
                "created_at":    j.get("created_at"),
                "_source":       "arbeitnow",
                "_search_query": query,
            })
        return result
    except Exception as exc:
        logger.warning("Arbeitnow error (q='%s' p=%d): %s", query, page, exc)
        return []


def _fetch_arbeitnow(queries, pages, limit, seen_ids):
    try:
        _validate_url(_ARBEITNOW_BASE)
    except ValueError as exc:
        logger.error("Arbeitnow blocked: %s", exc)
        return []

    jobs = []
    for query in queries:
        logger.info("  [Arbeitnow] '%s'", query)
        for page in range(1, pages + 1):
            page_jobs = _fetch_arbeitnow_page(query, page)
            for j in page_jobs:
                if j["job_id"] and j["job_id"] not in seen_ids:
                    seen_ids.add(j["job_id"])
                    jobs.append(j)
            if limit > 0 and len(jobs) >= limit:
                return jobs
            if page < pages:
                time.sleep(INTER_REQUEST_DELAY)
        time.sleep(INTER_REQUEST_DELAY)
        if limit > 0 and len(jobs) >= limit:
            break
    return jobs


# --- remotive ---

def _fetch_remotive_category(category: str) -> List[Dict[str, Any]]:
    parts = urlparse(_REMOTIVE_BASE)
    url = urlunparse(parts._replace(query=urlencode({"category": category, "limit": 50})))
    try:
        data = _get_json(url)
        raw_jobs = data.get("jobs", [])
        if not isinstance(raw_jobs, list):
            return []

        result = []
        for j in raw_jobs:
            result.append({
                "job_id":        f"remotive-{j.get('id', '')}",
                "title":         j.get("title", ""),
                "company":       j.get("company_name", ""),
                "location":      j.get("candidate_required_location", "Remote"),
                "remote":        True,
                "description":   j.get("description", ""),
                "url":           j.get("url", ""),
                "created_at":    None,
                "_source":       "remotive",
                "_search_query": f"remotive:{category}",
            })
        return result
    except Exception as exc:
        logger.warning("Remotive error (%s): %s", category, exc)
        return []


def _fetch_remotive(limit, seen_ids):
    try:
        _validate_url(_REMOTIVE_BASE)
    except ValueError as exc:
        logger.error("Remotive blocked: %s", exc)
        return []

    jobs = []
    for cat in _REMOTIVE_CATEGORIES:
        logger.info("  [Remotive] %s", cat)
        cat_jobs = _fetch_remotive_category(cat)
        for j in cat_jobs:
            if j["job_id"] and j["job_id"] not in seen_ids:
                seen_ids.add(j["job_id"])
                jobs.append(j)
        logger.info("    -> %d new jobs", len(cat_jobs))
        if limit > 0 and len(jobs) >= limit:
            break
        time.sleep(INTER_REQUEST_DELAY)
    return jobs


# --- public api ---

def fetch_jobs(search_queries=None, pages_per_query=None, max_jobs=None):
    """
    Fetch from all sources, deduplicate, return combined list.
    """
    queries = search_queries or settings.SEARCH_QUERIES
    pages = pages_per_query or settings.MAX_PAGES_PER_QUERY
    limit = max_jobs if max_jobs is not None else settings.MAX_JOBS_PER_RUN

    logger.info("Fetching jobs (limit: %d)", limit)

    seen_ids: Set[str] = set()
    all_jobs: List[Dict[str, Any]] = []

    # remotive first (remote-only, usually more relevant)
    remotive = _fetch_remotive(limit=limit, seen_ids=seen_ids)
    all_jobs.extend(remotive)
    logger.info("[Remotive] %d jobs", len(remotive))

    # then arbeitnow
    remaining = max(0, limit - len(all_jobs)) if limit > 0 else 0
    if remaining > 0 or limit <= 0:
        arbeitnow = _fetch_arbeitnow(queries, pages, remaining, seen_ids)
        all_jobs.extend(arbeitnow)
        logger.info("[Arbeitnow] %d jobs", len(arbeitnow))

    result = all_jobs[:limit] if limit > 0 else all_jobs
    logger.info("Total: %d unique jobs", len(result))
    return result
