import json

import pytest

from app.services.extraction import ExtractionError, extract_from_html

URL = "https://www.example.com/careers/42"

JOB_POSTING = {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    "title": "Data Engineer",
    "hiringOrganization": {"@type": "Organization", "name": "Globex"},
    "jobLocation": {
        "@type": "Place",
        "address": {"addressLocality": "Hyderabad", "addressRegion": "TS", "addressCountry": "IN"},
    },
    "employmentType": ["FULL_TIME"],
    "baseSalary": {
        "currency": "INR",
        "value": {"minValue": 1500000, "maxValue": 2500000, "unitText": "YEAR"},
    },
    "datePosted": "2026-10-01",
    "description": "<p>Build <b>pipelines</b>.</p><ul><li>Python</li></ul>",
}


def page(head: str = "", body: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_jsonld_extraction():
    html = page(f'<script type="application/ld+json">{json.dumps({"@graph": [JOB_POSTING]})}</script>')
    extractor, job = extract_from_html(URL, html)

    assert extractor == "jsonld"
    assert job.title == "Data Engineer"
    assert job.company == "Globex"
    assert job.location == "Hyderabad, TS, IN"
    assert job.employment_type == "FULL_TIME"
    assert job.salary == "INR 1500000 - 2500000 / YEAR"
    assert job.description == "Build\npipelines\n.\nPython"
    assert job.source == "example.com"


def test_generic_fallback():
    html = page('<meta property="og:title" content="QA Lead"><meta name="description" content="Test things">')
    extractor, job = extract_from_html(URL, html)

    assert extractor == "generic"
    assert job.title == "QA Lead"
    assert job.description == "Test things"


def test_nothing_found():
    with pytest.raises(ExtractionError):
        extract_from_html(URL, page())


def test_extract_endpoint_saves(client, monkeypatch):
    async def fake_fetch(url):
        return page(f'<script type="application/ld+json">{json.dumps(JOB_POSTING)}</script>')

    monkeypatch.setattr("app.services.extraction.fetch_html", fake_fetch)

    res = client.post("/api/v1/extract", json={"url": URL})
    assert res.status_code == 200
    body = res.json()
    assert body["extractor"] == "jsonld"
    assert body["saved_job"]["id"] > 0
    assert client.get("/api/v1/jobs").json()["total"] == 1
