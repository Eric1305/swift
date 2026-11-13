"""The call script. Code decides what is asked and what may be promised; the LLM only extracts facts."""
from pydantic import BaseModel, Field

STEPS = ["confirm_address", "people", "cant_leave", "water_inside", "can_help", "readback", "close"]

INTRO = "This is Swift, an automated flood assistant working with local emergency services."

BANNED = [
    "help is on the way", "on their way", "on the way to you", "we're sending", "we are sending",
    "someone is coming", "someone will come", "you'll be rescued", "you will be rescued",
    "you are safe", "you're safe", "estamos enviando", "ya van", "está a salvo", "esta a salvo",
]

TEMPLATES = {
    "needs_help": (
        "I've recorded that you need help leaving. No responder has been assigned yet. "
        "If water is rising inside, move to the highest floor and call 911 if you can get through."
    ),
    "can_help": (
        "I've recorded that you may be able to help neighbors. A dispatcher may contact you. "
        "Only go out if it's safe for you, and never drive into water you can't see the bottom of."
    ),
    "safe": (
        "I've recorded that everyone there can leave on their own. "
        "Don't drive through flooded roads. Turn around, don't drown."
    ),
    "unconfirmed": "I wasn't able to confirm everything, so a responder may follow up with you.",
}


class CanHelp(BaseModel):
    truck: bool = False
    boat: bool = False
    seats: int = 0


class Record(BaseModel):
    id: str
    address: str = ""
    status: str = "not_called"
    people: int | None = None
    cant_leave_alone: list[dict] = Field(default_factory=list)
    water_inside: bool | None = None
    can_help: CanHelp = Field(default_factory=CanHelp)
    language: str = "en"
    transcript: list[dict] = Field(default_factory=list)
    house_card: str | None = None
    attempts: int = 0


class CallState(BaseModel):
    record: Record
    step: str = STEPS[0]
    reasked: bool = False


def guard(text: str) -> str:
    """Blank any LLM text that implies help is coming or that the person is safe."""
    lowered = text.lower().replace("’", "'")
    return "" if any(phrase in lowered for phrase in BANNED) else text


def status_of(rec: Record) -> str:
    if rec.cant_leave_alone or rec.water_inside:
        return "needs_help"
    if rec.can_help.truck or rec.can_help.boat or rec.can_help.seats > 0:
        return "can_help"
    if rec.people is not None:
        return "safe"
    return "unconfirmed"


def _readback(rec: Record) -> str:
    parts = [f"{rec.people} people" if rec.people is not None else "people at the home not confirmed"]
    for person in rec.cant_leave_alone:
        parts.append(f"{person.get('who', 'someone')} needs help leaving because of {person.get('need', 'a condition')}")
    if rec.water_inside is not None:
        parts.append("water is inside" if rec.water_inside else "no water inside yet")
    vehicles = [name for name, has in (("a truck", rec.can_help.truck), ("a boat", rec.can_help.boat)) if has]
    if rec.can_help.seats:
        vehicles.append(f"{rec.can_help.seats} free seats")
    if vehicles:
        parts.append("you can help with " + " and ".join(vehicles))
    return "Let me read that back: " + "; ".join(parts) + ". Is that right?"


def prompt_for(state: CallState) -> str:
    rec = state.record
    return {
        "confirm_address": f"Am I speaking with someone at {rec.address}?",
        "people": "How many people are at the home right now, including anyone who can't come to the phone?",
        "cant_leave": (
            "Is there anyone there who can't leave on their own, for example someone who uses a wheelchair, "
            "needs oxygen, or is bedbound? If it's a wheelchair, does it have a motor?"
        ),
        "water_inside": "Is there water inside the home right now?",
        "can_help": "If neighbors need a ride out, do you have a high-clearance truck, a boat, or free seats in a vehicle?",
        "readback": _readback(rec),
        "close": TEMPLATES[status_of(rec)] + " Goodbye.",
    }[state.step]


def _merge(rec: Record, fields: dict) -> Record:
    data = rec.model_dump()
    if "people" in fields:
        data["people"] = fields["people"]
    for person in fields.get("cant_leave_alone") or []:
        if person not in data["cant_leave_alone"]:
            data["cant_leave_alone"].append(person)  # never dropped once recorded
    if "water_inside" in fields:
        data["water_inside"] = fields["water_inside"]
    if "can_help" in fields:
        data["can_help"] = {**data["can_help"], **fields["can_help"]}
    if "language" in fields:
        data["language"] = fields["language"]
    merged = Record.model_validate(data)
    merged.status = status_of(merged)
    return merged


def advance(state: CallState, fields: dict, ack: str) -> tuple[CallState, str]:
    """Apply one caller turn. Empty input re-asks once, then moves on. Returns the new state and the line to speak."""
    if not fields and not ack and not state.reasked and state.step != "close":
        new = state.model_copy(update={"reasked": True})
        return new, "Sorry, I didn't catch that. " + prompt_for(new)
    record = _merge(state.record, fields)
    next_step = STEPS[min(STEPS.index(state.step) + 1, len(STEPS) - 1)]
    new = CallState(record=record, step=next_step, reasked=False)
    safe_ack = guard(ack).strip()
    return new, (safe_ack + " " if safe_ack else "") + prompt_for(new)
