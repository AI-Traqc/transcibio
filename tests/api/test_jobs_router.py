from types import SimpleNamespace

from backend.app.api.routers.jobs import _parse_job_payload, _to_job_response


def test_parse_job_payload_accepts_json_object_string():
    assert _parse_job_payload('{"status":"done"}') == {"status": "done"}


def test_to_job_response_parses_stored_json_strings():
    record = SimpleNamespace(
        id="job-1",
        session_id="session-1",
        job_type="transcribe_audio",
        status="completed",
        progress=1.0,
        created_at_utc="2026-03-06T12:00:00Z",
        started_at_utc="2026-03-06T12:00:01Z",
        finished_at_utc="2026-03-06T12:00:02Z",
        input_json='{"session_id":"session-1","diarization_enabled":true}',
        output_json='{"speaker_count":2,"warnings":[]}',
        error_message="",
    )

    response = _to_job_response(record)

    assert response.input_json == {"session_id": "session-1", "diarization_enabled": True}
    assert response.output_json == {"speaker_count": 2, "warnings": []}
