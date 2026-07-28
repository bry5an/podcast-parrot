from datetime import datetime, timedelta

from app.models import (
    Episode,
    Podcast,
    Profile,
    Sentence,
    ShadowEvent,
    Transcript,
    TranscriptSource,
)


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


def test_update_position_creates_then_upserts(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    response = client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/position", json={"position_seconds": 12.5}
    )
    assert response.status_code == 200
    assert response.json()["position_seconds"] == 12.5

    response = client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/position", json={"position_seconds": 40.0}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["position_seconds"] == 40.0

    # Upsert, not a second row.
    listing = client.get(f"/api/podcasts/{podcast.id}/episodes", params={"profile_id": profile.id})
    matches = [e for e in listing.json() if e["id"] == episode.id]
    assert len(matches) == 1
    assert matches[0]["position_seconds"] == 40.0


def test_update_position_missing_profile_returns_404(client, session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    response = client.post(f"/api/profiles/999/episodes/{episode.id}/position", json={"position_seconds": 1})
    assert response.status_code == 404


def test_update_position_missing_episode_returns_404(client, session):
    profile = _make_profile(session)
    response = client.post(f"/api/profiles/{profile.id}/episodes/999/position", json={"position_seconds": 1})
    assert response.status_code == 404


def test_log_shadow_event(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 2)

    response = client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow",
        json={"sentence_id": sentences[0].id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["profile_id"] == profile.id
    assert body["episode_id"] == episode.id
    assert body["sentence_id"] == sentences[0].id


def test_log_shadow_event_missing_sentence_returns_404(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    response = client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow", json={"sentence_id": 999}
    )
    assert response.status_code == 404


def test_log_shadow_event_sentence_from_other_episode_returns_404(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast, guid="ep-1", title="Episode 1")
    other_episode = _make_episode(session, podcast, guid="ep-2", title="Episode 2")
    other_sentences = _make_sentences(session, other_episode, 1)

    response = client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow",
        json={"sentence_id": other_sentences[0].id},
    )
    assert response.status_code == 404


def test_shadow_summary_counts_distinct_sentences_today(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 3)

    # Shadowing the same sentence twice shouldn't double-count.
    client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow", json={"sentence_id": sentences[0].id}
    )
    client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow", json={"sentence_id": sentences[0].id}
    )
    client.post(
        f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow", json={"sentence_id": sentences[1].id}
    )

    response = client.get(f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow-summary")
    assert response.status_code == 200
    assert response.json() == {"doneToday": 2, "total": 3}


def test_shadow_summary_excludes_events_from_other_days(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 2)

    yesterday_event = ShadowEvent(
        profile_id=profile.id,
        episode_id=episode.id,
        sentence_id=sentences[0].id,
        shadowed_at=datetime.utcnow() - timedelta(days=1),
    )
    session.add(yesterday_event)
    session.commit()

    response = client.get(f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow-summary")
    assert response.status_code == 200
    assert response.json() == {"doneToday": 0, "total": 2}


def test_shadow_summary_without_transcript_has_zero_total(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)

    response = client.get(f"/api/profiles/{profile.id}/episodes/{episode.id}/shadow-summary")
    assert response.status_code == 200
    assert response.json() == {"doneToday": 0, "total": 0}


def test_shadow_summary_missing_profile_returns_404(client, session):
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    response = client.get(f"/api/profiles/999/episodes/{episode.id}/shadow-summary")
    assert response.status_code == 404


def test_streak_zero_with_no_events(client, session):
    profile = _make_profile(session)
    response = client.get(f"/api/profiles/{profile.id}/streak")
    assert response.status_code == 200
    assert response.json() == {"streak": 0}


def _seed_event(session, profile, episode, sentence, days_ago: int) -> None:
    session.add(
        ShadowEvent(
            profile_id=profile.id,
            episode_id=episode.id,
            sentence_id=sentence.id,
            shadowed_at=datetime.utcnow() - timedelta(days=days_ago),
        )
    )
    session.commit()


def test_streak_counts_consecutive_days_including_today(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    for days_ago in (0, 1, 2):
        _seed_event(session, profile, episode, sentences[0], days_ago)

    response = client.get(f"/api/profiles/{profile.id}/streak")
    assert response.status_code == 200
    assert response.json() == {"streak": 3}


def test_streak_breaks_on_gap(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    for days_ago in (0, 1, 3):  # gap at 2 days ago
        _seed_event(session, profile, episode, sentences[0], days_ago)

    response = client.get(f"/api/profiles/{profile.id}/streak")
    assert response.status_code == 200
    assert response.json() == {"streak": 2}


def test_streak_stays_alive_before_todays_first_event(client, session):
    profile = _make_profile(session)
    podcast = _make_podcast(session)
    episode = _make_episode(session, podcast)
    sentences = _make_sentences(session, episode, 1)

    # No event yet today, but yesterday and the day before are shadowed —
    # the streak shouldn't reset to 0 just because today hasn't happened yet.
    for days_ago in (1, 2):
        _seed_event(session, profile, episode, sentences[0], days_ago)

    response = client.get(f"/api/profiles/{profile.id}/streak")
    assert response.status_code == 200
    assert response.json() == {"streak": 2}


def test_streak_missing_profile_returns_404(client):
    response = client.get("/api/profiles/999/streak")
    assert response.status_code == 404
