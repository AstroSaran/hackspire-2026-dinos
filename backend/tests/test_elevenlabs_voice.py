from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main


class JsonResponse:
    status_code = 200
    ok = True
    content = b"fake-mp3-bytes"

    def json(self):
        return {"text": "আজকের আবহাওয়া"}


def _client():
    main._rate_events.clear()
    return TestClient(main.app)


def test_transcription_prefers_elevenlabs_and_sends_bn_language(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with patch("app.main.requests.post", return_value=JsonResponse()) as post:
        response = _client().post("/support/transcribe", files={
            "audio": ("sample.webm", b"fake audio bytes", "audio/webm")},
            data={"language": "bn-IN"})

    assert response.status_code == 200
    assert response.json()["transcript"] == "আজকের আবহাওয়া"
    assert response.json()["provider"] == "ElevenLabs"
    assert post.call_args.args[0] == "https://api.elevenlabs.io/v1/speech-to-text"
    assert post.call_args.kwargs["data"]["language_code"] == "ben"
    assert "test-eleven-secret" not in response.text


def test_speech_generation_returns_audio_and_keeps_key_server_side(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-secret")
    with patch("app.main.requests.post", return_value=JsonResponse()) as post:
        response = _client().post("/voice/synthesize", json={
            "text": "আজকের আবহাওয়া ভালো", "voice_id": "voice123456"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"fake-mp3-bytes"
    assert post.call_args.args[0].endswith("/voice123456")
    assert post.call_args.kwargs["headers"]["xi-api-key"] == "test-eleven-secret"


def test_voice_cloning_requires_explicit_speaker_and_provider_consent(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-secret")
    client = _client()
    with patch("app.main.requests.post") as post:
        response = client.post("/voice/clone", data={"name": "My voice"}, files=[
            ("files", ("sample.wav", b"sample audio", "audio/wav"))])
    assert response.status_code == 400
    post.assert_not_called()


def test_voice_cloning_returns_id_but_does_not_claim_sample_is_saved(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-secret")
    result = JsonResponse()
    result.json = lambda: {"voice_id": "voice123456", "requires_verification": True}
    with patch("app.main.requests.post", return_value=result):
        response = _client().post("/voice/clone", data={"name": "My voice", "consent": "true",
            "speaker_authorized": "true"}, files=[
                ("files", ("sample.wav", b"sample audio", "audio/wav"))])

    assert response.status_code == 200
    assert response.json() == {"voice_id": "voice123456", "requires_verification": True,
                               "sample_stored_by_kavach": False}
