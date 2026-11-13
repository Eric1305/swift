from agent import store
from agent.script import Record


def test_call_and_household_round_trip(tmp_path):
    conn = store.connect(tmp_path / "t.db")
    rec = Record(id="h095", address="1 Test Ln", people=2, status="needs_help",
                 cant_leave_alone=[{"who": "mom", "need": "power wheelchair"}], water_inside=False,
                 transcript=[{"who": "agent", "text": "hi"}, {"who": "resident", "text": "two of us"}])
    store.save_call("call_1", rec, "in-progress", conn=conn)
    rec.house_card = "2 people; mom, power wheelchair"
    store.save_call("call_1", rec, "completed", conn=conn)
    home = store.households(conn)[0]
    assert home["people"] == 2 and home["cant_leave_alone"] == [{"who": "mom", "need": "power wheelchair"}]
    assert home["water_inside"] == 0 and home["house_card"].startswith("2 people")
    call = store.calls_for("h095", conn)[0]
    assert call["call_status"] == "completed" and len(call["transcript"]) == 2
