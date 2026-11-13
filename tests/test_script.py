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
    state, _ = advance(state.model_copy(update={"step": "fix"}), {"people": 3}, "Thanks.")
    assert state.record.people == 3
    assert len(state.record.cant_leave_alone) == 1


def test_reask_when_answer_does_not_fit():
    state, text = advance(new_state("people"), {}, "Thank you for confirming that.")
    assert state.step == "people" and state.reasked
    assert "Thank you for confirming" not in text
    state, _ = advance(state, {"people": 2}, "Got it.")
    assert state.record.people == 2 and state.step == "cant_leave"


def test_bare_yes_to_cant_leave_asks_who():
    state, text = advance(new_state("cant_leave"), {"someone": True, "cant_leave_alone": []}, "Okay.")
    assert state.step == "cant_leave_detail" and state.record.cant_leave_alone == []
    assert "Who is it" in text
    state, _ = advance(state, {"cant_leave_alone": [{"who": "mom", "need": "power wheelchair"}]}, "Thanks.")
    assert state.step == "water_inside"
    assert state.record.cant_leave_alone == [{"who": "mom", "need": "power wheelchair"}]


def test_volunteered_facts_fill_gaps_only():
    state, _ = advance(new_state("water_inside"),
                       {"water_inside": False, "people": 2,
                        "cant_leave_alone": [{"who": "mom", "need": "power wheelchair"}]}, "Okay.")
    assert state.record.people == 2 and len(state.record.cant_leave_alone) == 1
    state, _ = advance(state, {"can_help": {"truck": False, "boat": False, "seats": 0}, "people": 5}, "Okay.")
    assert state.record.people == 2  # out-of-turn mention doesn't overwrite an answer


def test_negative_readback_gets_one_fix_round():
    state, text = advance(new_state("readback"), {"correct": False}, "I hear you.")
    assert state.step == "fix" and "What should I fix" in text
    state, text = advance(state, {"people": 3}, "Thanks.")
    assert state.step == "readback" and state.corrected and "3 people" in text
    state, _ = advance(state, {"correct": False}, "Okay.")
    assert state.step == "close"


def test_status_rules():
    assert status_of(Record(id="a", cant_leave_alone=[{"who": "dad", "need": "walker"}])) == "needs_help"
    assert status_of(Record(id="b", water_inside=True)) == "needs_help"
    assert status_of(Record(id="c", people=2, can_help={"truck": True, "boat": False, "seats": 0})) == "can_help"
    assert status_of(Record(id="d", people=2, can_help={"truck": False, "boat": False, "seats": 3})) == "can_help"
    assert status_of(Record(id="e", people=4)) == "safe"
    assert status_of(Record(id="f")) == "unconfirmed"


def test_nothing_to_fix_closes_the_call():
    state, _ = advance(new_state("fix"), {"no_change": True}, "Okay.")
    assert state.step == "close"


def test_same_person_twice_is_one_entry():
    state, _ = advance(new_state("cant_leave"),
                       {"cant_leave_alone": [{"who": "mom", "need": "power wheelchair"}]}, "Okay.")
    state, _ = advance(state.model_copy(update={"step": "fix"}),
                       {"cant_leave_alone": [{"who": "her mom", "need": "motorized wheelchair"},
                                             {"who": "dad", "need": "uses a wheelchair"}]}, "Okay.")
    assert state.record.cant_leave_alone == [{"who": "mom", "need": "power wheelchair"},
                                             {"who": "dad", "need": "uses a wheelchair"}]
