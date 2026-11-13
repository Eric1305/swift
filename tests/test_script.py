from agent.script import CallState, Record, advance, guard, status_of


def new_state(step="people"):
    return CallState(record=Record(id="h003", address="2207 Rolling Oak Ln"), step=step)


def test_guard_blanks_promises():
    assert guard("Okay, help is on the way!") == ""
    assert guard("Estamos enviando a alguien.") == ""
    assert guard("Got it, thank you.") == "Got it, thank you."


def test_empty_reply_reasks_once():
    state, _ = advance(new_state("people"), {}, "")
    assert state.step == "people"
    assert state.reasked is True
    state, _ = advance(state, {}, "")
    assert state.step == "cant_leave"


def test_correction_keeps_cant_leave():
    state, _ = advance(
        new_state("people"),
        {"people": 2, "cant_leave_alone": [{"who": "mother", "need": "power wheelchair"}]},
        "Got it.",
    )
    state, _ = advance(state, {"people": 3}, "Thanks.")
    assert state.record.people == 3
    assert len(state.record.cant_leave_alone) == 1


def test_status_rules():
    assert status_of(Record(id="a", cant_leave_alone=[{"who": "dad", "need": "walker"}])) == "needs_help"
    assert status_of(Record(id="b", water_inside=True)) == "needs_help"
    assert status_of(Record(id="c", people=2, can_help={"truck": True, "boat": False, "seats": 0})) == "can_help"
    assert status_of(Record(id="d", people=2, can_help={"truck": False, "boat": False, "seats": 3})) == "can_help"
    assert status_of(Record(id="e", people=4)) == "safe"
    assert status_of(Record(id="f")) == "unconfirmed"
