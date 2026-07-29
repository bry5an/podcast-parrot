from app.models import Episode, Podcast, Profile, Sentence, Transcript, TranscriptSource


def _make_profile(session, **overrides) -> Profile:
    defaults = dict(name="Kenji")
    defaults.update(overrides)
    profile = Profile(**defaults)
    session.add(profile)
    session.commit()
    session.refresh(profile)
    return profile


def _make_podcast(session, **overrides) -> Podcast:
    defaults = dict(rss_url="https://example.com/feed.xml", title="Nihongo News", language="ja")
    defaults.update(overrides)
    podcast = Podcast(**defaults)
    session.add(podcast)
    session.commit()
    session.refresh(podcast)
    return podcast


def _make_episode(session, podcast: Podcast, **overrides) -> Episode:
    defaults = dict(
        podcast_id=podcast.id,
        guid=f"guid-{overrides.get('title', 'episode')}",
        title="Episode",
        audio_url="https://example.com/audio.mp3",
    )
    defaults.update(overrides)
    episode = Episode(**defaults)
    session.add(episode)
    session.commit()
    session.refresh(episode)
    return episode


def _make_sentences(session, episode: Episode, count: int) -> list[Sentence]:
    transcript = Transcript(episode_id=episode.id, language="ja", source=TranscriptSource.published)
    session.add(transcript)
    session.commit()
    session.refresh(transcript)

    sentences = []
    for i in range(count):
        sentence = Sentence(
            transcript_id=transcript.id,
            index=i,
            start_time=float(i),
            end_time=float(i + 1),
            text=f"sentence {i}",
            segments=[],
        )
        session.add(sentence)
        session.commit()
        session.refresh(sentence)
        sentences.append(sentence)
    return sentences


def test_create_and_list_saved_sentence(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, local_audio_path="episode.mp3")
    sentences = _make_sentences(session, episode, 3)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "greeting",
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[1].id,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "greeting"
    assert body["profile_id"] == profile.id
    assert body["episode_id"] == episode.id
    assert body["podcast_id"] == podcast.id
    assert body["podcast_title"] == "Nihongo News"
    assert body["episode_title"] == "Episode"
    assert body["text"] == "sentence 0 sentence 1"
    assert body["start_time"] == 0.0
    assert body["end_time"] == 2.0
    assert body["audio_available"] is True

    listing = client.get(f"/api/profiles/{profile.id}/saved-sentences")
    assert listing.status_code == 200
    assert [c["id"] for c in listing.json()] == [body["id"]]


def test_create_saved_sentence_single_sentence(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "single",
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[0].id,
        },
    )
    assert response.status_code == 201
    assert response.json()["audio_available"] is False


def test_create_saved_sentence_missing_profile_returns_404(client, session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    response = client.post(
        "/api/profiles/999/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "x",
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[0].id,
        },
    )
    assert response.status_code == 404


def test_create_saved_sentence_missing_episode_returns_404(client, session):
    profile = _make_profile(session)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={"episode_id": 999, "name": "x", "start_sentence_id": 1, "end_sentence_id": 1},
    )
    assert response.status_code == 404


def test_create_saved_sentence_sentence_from_other_episode_returns_404(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, guid="ep-1", title="Episode 1")
    other_episode = _make_episode(session, podcast, guid="ep-2", title="Episode 2")
    own_sentences = _make_sentences(session, episode, 1)
    other_sentences = _make_sentences(session, other_episode, 1)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "x",
            "start_sentence_id": own_sentences[0].id,
            "end_sentence_id": other_sentences[0].id,
        },
    )
    assert response.status_code == 404


def test_create_saved_sentence_rejects_more_than_five_sentences(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 6)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "too many",
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[5].id,
        },
    )
    assert response.status_code == 422


def test_create_saved_sentence_rejects_reversed_range(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 2)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "backwards",
            "start_sentence_id": sentences[1].id,
            "end_sentence_id": sentences[0].id,
        },
    )
    assert response.status_code == 422


def test_create_saved_sentence_rejects_empty_name(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": "   ",
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[0].id,
        },
    )
    assert response.status_code == 422


def _create_clip(client, profile, episode, sentences, name="clip"):
    response = client.post(
        f"/api/profiles/{profile.id}/saved-sentences",
        json={
            "episode_id": episode.id,
            "name": name,
            "start_sentence_id": sentences[0].id,
            "end_sentence_id": sentences[0].id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_rename_saved_sentence(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)
    clip = _create_clip(client, profile, episode, sentences)

    response = client.patch(
        f"/api/profiles/{profile.id}/saved-sentences/{clip['id']}", json={"name": "renamed"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_rename_saved_sentence_missing_returns_404(client, session):
    profile = _make_profile(session)
    response = client.patch(f"/api/profiles/{profile.id}/saved-sentences/999", json={"name": "x"})
    assert response.status_code == 404


def test_rename_saved_sentence_wrong_profile_returns_404(client, session):
    profile = _make_profile(session)
    other_profile = _make_profile(session, name="Other")
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)
    clip = _create_clip(client, profile, episode, sentences)

    response = client.patch(
        f"/api/profiles/{other_profile.id}/saved-sentences/{clip['id']}", json={"name": "hijack"}
    )
    assert response.status_code == 404


def test_rename_saved_sentence_rejects_empty_name(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)
    clip = _create_clip(client, profile, episode, sentences)

    response = client.patch(f"/api/profiles/{profile.id}/saved-sentences/{clip['id']}", json={"name": " "})
    assert response.status_code == 422


def test_delete_saved_sentence(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)
    clip = _create_clip(client, profile, episode, sentences)

    response = client.delete(f"/api/profiles/{profile.id}/saved-sentences/{clip['id']}")
    assert response.status_code == 204

    listing = client.get(f"/api/profiles/{profile.id}/saved-sentences")
    assert listing.json() == []


def test_delete_saved_sentence_wrong_profile_returns_404(client, session):
    profile = _make_profile(session)
    other_profile = _make_profile(session, name="Other")
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)
    clip = _create_clip(client, profile, episode, sentences)

    response = client.delete(f"/api/profiles/{other_profile.id}/saved-sentences/{clip['id']}")
    assert response.status_code == 404
