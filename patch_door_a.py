with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

old_door = """
def _door_a_pick(audio: Any, s1: str, s2: str) -> str | None:
    \"\"\"Door A 2-candidate keypad turn (T12): name both, press 1/2/3.

    Returns "1"/"2" (picked), "hangup", or None (0/3/anything else declines).
    One turn, no repeats.
    \"\"\"
    audio.say(("door_a_option_1", scheme_name_chunk(s1),
               "door_a_option_2", scheme_name_chunk(s2),
               "door_a_option_none"))
    pick = audio.next_input(profile="normal")
    if isinstance(pick, Hangup):
        return "hangup"
    if isinstance(pick, Digit) and pick.digit in ("1", "2"):
        return pick.digit
    return None
"""

new_door = """
def _door_a_pick(audio: Any, log: Any, s1: str, s2: str) -> str | None:
    \"\"\"Door A 2-candidate keypad turn (T12): name both, press 1/2/3.

    Returns "1"/"2" (picked), "hangup", or None (0/3/anything else declines).
    One turn, no repeats.
    \"\"\"
    try:
        pick = Engine._wait_for_input(
            audio, log,
            ("door_a_option_1", scheme_name_chunk(s1),
             "door_a_option_2", scheme_name_chunk(s2),
             "door_a_option_none"),
            "normal",
            valid_keys=("1", "2", "3", "0")
        )
    except EngineDropCall as e:
        return "hangup"
    if isinstance(pick, Hangup):
        return "hangup"
    if isinstance(pick, Digit) and pick.digit in ("1", "2"):
        return pick.digit
    return None
"""

content = content.replace(old_door, new_door)
content = content.replace("outcome = _door_a_pick(audio, s1, s2)", "outcome = _door_a_pick(audio, log, s1, s2)")
content = content.replace("outcome = _door_a_pick(audio, model_ids[0], model_ids[1])", "outcome = _door_a_pick(audio, log, model_ids[0], model_ids[1])")

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
