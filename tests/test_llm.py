from types import SimpleNamespace

import agent.llm as llm


def fake_client(text):
    message = SimpleNamespace(content=text)
    completion = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    create = lambda **kwargs: completion
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_bad_json_returns_empty_fields(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: fake_client("sure! here you go"))
    assert llm.extract("people", "it's me and my mom") == ({}, "")


def test_extract_keeps_only_step_keys(monkeypatch):
    reply = '{"people": 2, "water_inside": true, "ack": "Got it, two people."}'
    monkeypatch.setattr(llm, "_client", lambda: fake_client(reply))
    assert llm.extract("people", "two of us") == ({"people": 2}, "Got it, two people.")
