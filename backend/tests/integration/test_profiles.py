from sqlmodel import select

from app.models import (
    Episode,
    PlaybackState,
    Podcast,
    SavedSentence,
    Sentence,
    ShadowEvent,
    Subscription,
    Transcript,
)


def test_create_profile(client):
    response = client.post("/api/profiles", json={"name": "Kenji"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Kenji"
    assert body["learning_language"] == "ja"
    assert body["show_furigana"] is True
    assert body["id"] is not None


def test_create_profile_rejects_blank_name(client):
    response = client.post("/api/profiles", json={"name": "   "})
    assert response.status_code == 422


def test_list_profiles(client):
    client.post("/api/profiles", json={"name": "Kenji"})
    client.post("/api/profiles", json={"name": "Aoi"})

    response = client.get("/api/profiles")
    assert response.status_code == 200
    names = {p["name"] for p in response.json()}
    assert names == {"Kenji", "Aoi"}


def test_get_profile(client):
    created = client.post("/api/profiles", json={"name": "Kenji"}).json()

    response = client.get(f"/api/profiles/{created['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Kenji"


def test_get_profile_missing_returns_404(client):
    response = client.get("/api/profiles/999")
    assert response.status_code == 404


def test_update_profile_partial(client):
    created = client.post("/api/profiles", json={"name": "Kenji", "show_furigana": True}).json()

    response = client.patch(f"/api/profiles/{created['id']}", json={"show_furigana": False})
    assert response.status_code == 200
    body = response.json()
    assert body["show_furigana"] is False
    assert body["name"] == "Kenji"  # untouched fields survive a partial update


def test_update_profile_last_used_at(client):
    created = client.post("/api/profiles", json={"name": "Kenji"}).json()
    assert created["last_used_at"] is None

    response = client.patch(f"/api/profiles/{created['id']}", json={"last_used_at": "2026-07-31T12:00:00"})
    assert response.status_code == 200
    body = response.json()
    assert body["last_used_at"] == "2026-07-31T12:00:00"
    assert body["name"] == "Kenji"  # untouched fields survive a partial update


def test_update_profile_missing_returns_404(client):
    response = client.patch("/api/profiles/999", json={"name": "Nope"})
    assert response.status_code == 404


def test_delete_profile(client):
    created = client.post("/api/profiles", json={"name": "Kenji"}).json()

    response = client.delete(f"/api/profiles/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/profiles/{created['id']}").status_code == 404


def test_delete_profile_missing_returns_404(client):
    response = client.delete("/api/profiles/999")
    assert response.status_code == 404


def test_delete_profile_clears_dependent_rows(client, session):
    profile_id = client.post("/api/profiles", json={"name": "Kenji"}).json()["id"]

    podcast = Podcast(rss_url="https://example.com/a.xml", title="Nihongo News", language="ja")
    session.add(podcast)
    session.commit()
    session.refresh(podcast)

    episode = Episode(podcast_id=podcast.id, guid="1", title="Ep 1", audio_url="https://example.com/1.mp3")
    session.add(episode)
    session.commit()
    session.refresh(episode)

    transcript = Transcript(episode_id=episode.id)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)

    sentence = Sentence(transcript_id=transcript.id, index=0, start_time=0, end_time=1, text="こんにちは")
    session.add(sentence)
    session.commit()
    session.refresh(sentence)

    session.add(Subscription(profile_id=profile_id, podcast_id=podcast.id))
    session.add(PlaybackState(profile_id=profile_id, episode_id=episode.id, position_seconds=12))
    session.add(
        SavedSentence(
            profile_id=profile_id,
            episode_id=episode.id,
            name="Clip",
            start_sentence_id=sentence.id,
            end_sentence_id=sentence.id,
        )
    )
    session.add(ShadowEvent(profile_id=profile_id, episode_id=episode.id, sentence_id=sentence.id))
    session.commit()

    response = client.delete(f"/api/profiles/{profile_id}")
    assert response.status_code == 204

    assert session.exec(select(Subscription).where(Subscription.profile_id == profile_id)).first() is None
    assert session.exec(select(PlaybackState).where(PlaybackState.profile_id == profile_id)).first() is None
    assert session.exec(select(SavedSentence).where(SavedSentence.profile_id == profile_id)).first() is None
    assert session.exec(select(ShadowEvent).where(ShadowEvent.profile_id == profile_id)).first() is None
    # Podcast/episode/sentence rows aren't profile-scoped, so they survive.
    assert session.get(Podcast, podcast.id) is not None
