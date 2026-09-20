"""Small HTTP factories shared by API and repository tests."""

from fastapi.testclient import TestClient


def create_bot(client: TestClient, *, name: str = "Mira") -> dict[str, object]:
    response = client.post(
        "/api/v1/bots",
        json={
            "name": name,
            "role_title": "Editorial research partner",
            "description": "Finds the signal in a crowded brief.",
            "system_instructions": "Lead with evidence and write in crisp, short paragraphs.",
            "avatar_value": "M",
        },
    )
    assert response.status_code == 201
    return response.json()
