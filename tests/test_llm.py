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


def test_question_words_are_not_invented(monkeypatch):
    reply = '{"someone": true, "cant_leave_alone": [{"who": "wheelchair", "need": "manual"}], "people": null, "ack": "Okay."}'
    monkeypatch.setattr(llm, "_client", lambda: fake_client(reply))
    fields, _ = llm.extract("cant_leave", "Yes.")
    assert "cant_leave_alone" not in fields and fields.get("someone") is True


def test_volunteered_people_are_kept_when_said(monkeypatch):
    reply = ('{"water_inside": true, "people": 2, "cant_leave_alone": [{"who": "mom", "need": "power wheelchair"}],'
             ' "ack": "Okay."}')
    monkeypatch.setattr(llm, "_client", lambda: fake_client(reply))
    fields, _ = llm.extract("water_inside", "Yes. Me and my mom. My mom uses a power wheelchair.")
    assert fields["people"] == 2 and fields["cant_leave_alone"] == [{"who": "mom", "need": "power wheelchair"}]


def test_plain_no_answers_can_help(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: fake_client('{"truck": null, "boat": null, "seats": null, "ack": "Okay."}'))
    assert llm.extract("can_help", "No, sorry.")[0] == {"can_help": {"truck": False, "boat": False, "seats": 0}}


def test_plain_no_to_readback_means_incorrect(monkeypatch):
    monkeypatch.setattr(llm, "_client", lambda: fake_client('{"correct": null, "people": null, "ack": "Okay."}'))
    assert llm.extract("readback", "No. I do not.")[0]["correct"] is False


def test_chatty_negatives_are_not_people(monkeypatch):
    reply = ('{"water_inside": false, "people": 3, "cant_leave_alone": [{"who": "everyone", "need": "no need"},'
             ' {"who": "us", "need": "no truck or boat or seats"}], "ack": "Okay."}')
    monkeypatch.setattr(llm, "_client", lambda: fake_client(reply))
    fields, _ = llm.extract("water_inside", "No water, everyone's fine, no need for a truck or boat or seats, three of us.")
    assert "cant_leave_alone" not in fields and fields["water_inside"] is False
