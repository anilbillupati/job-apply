API = "/api/v1"

SAMPLE = {
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Remote",
    "source_url": "https://example.com/jobs/1",
}


def test_health(client):
    assert client.get(f"{API}/health").json() == {"status": "ok"}


def test_job_crud(client):
    created = client.post(f"{API}/jobs", json=SAMPLE)
    assert created.status_code == 201
    job = created.json()
    assert job["status"] == "new"

    listed = client.get(f"{API}/jobs", params={"q": "acme"}).json()
    assert listed["total"] == 1

    updated = client.patch(f"{API}/jobs/{job['id']}", json={"status": "applied", "notes": "Sent CV"})
    assert updated.json()["status"] == "applied"

    assert client.get(f"{API}/jobs", params={"status": "new"}).json()["total"] == 0

    assert client.delete(f"{API}/jobs/{job['id']}").status_code == 204
    assert client.get(f"{API}/jobs/{job['id']}").status_code == 404


def test_upsert_keeps_user_status(client):
    job = client.post(f"{API}/jobs", json=SAMPLE).json()
    client.patch(f"{API}/jobs/{job['id']}", json={"status": "applied"})

    again = client.post(f"{API}/jobs", json={**SAMPLE, "title": "Senior Backend Engineer"}).json()
    assert again["id"] == job["id"]
    assert again["title"] == "Senior Backend Engineer"
    assert again["status"] == "applied"
