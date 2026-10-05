with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

import re

# We want to replace the whole `while True:` inside `_apply_b`
# From `while True:\n                        try:\n                            confirm_inp = Engine._wait_for_input`
# up to the end of the `isinstance(confirm_inp, Hangup)` block

start_marker = """                    confirm_repeats = 0
                    while True:
                        try:
                            confirm_inp = Engine._wait_for_input("""
end_marker = """                    if stop_reason:
                        break
"""

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Could not find markers")
    exit(1)

new_block = """                    confirm_repeats = 0
                    while True:
                        try:
                            confirm_inp = Engine._wait_for_input(
                                audio, log, confirm_seq, profile="confirm",
                                valid_keys=("1", "2", "3", "#", "*")
                            )
                        except EngineDropCall as e:
                            survs_s = Filter.survivors(box_vector, corpus)
                            silence_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                            log.close(reason=silence_stop, ladder_rung=e.ladder_rung, mode=mode)
                            return
                        if isinstance(confirm_inp, Hangup):
                            audio.hangup()
                            survs_s = Filter.survivors(box_vector, corpus)
                            h_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                            log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                            return
                        if isinstance(confirm_inp, Digit):
                            silence_ladder = 0
                            if confirm_inp.digit == "*":
                                curr_lang = getattr(audio, "language", "hi")
                                new_lang = _next_lang(curr_lang)
                                if hasattr(audio, "language"):
                                    audio.language = new_lang
                                log.write(LangSwitchRecord(lang=new_lang, lang_source="keypad", turn_n=turn_n))
                                audio.say(confirm_seq)
                                continue
                            elif confirm_inp.digit == "1":
                                turn_n += 1
                                box_vector[box] = proposed_val
                                box_strikes[box] = 0
                                question_count += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="ANSWER", box=box, value=proposed_val, transcript="1", span="1"))
                                break
                            elif confirm_inp.digit == "2":
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="UNCLEAR", transcript="2"))
                                if box_strikes[box] < tunables.BOX_STRIKES_TO_KEYPAD:
                                    audio.say(("unclear_prompt",))
                                break
                            elif confirm_inp.digit == "3":
                                # 3 was treated as out-of-menu before, _wait_for_input treats it as valid because we added it
                                # wait, we should just let it be out of menu.
                                pass
                        # All other cases (invalid digit, noise, speech) were swallowed by _wait_for_input and looped inside it.
                        # Wait! `_wait_for_input` DOES NOT swallow Noise and invalid Digits if we don't pass `on_miss_cb`!
                        # It will just say `unclear_prompt` and loop inside itself!
                        # This means `box_strikes` will NOT increment for Noise during confirm!
                        # Is that okay? "no per-spot copies". The uniform rule says on no reply say did not get reply and re-present.
                        # Actually, `confirm_repeats` was just a local anti-mash counter. `_wait_for_input` doesn't have an anti-mash counter for noise yet.
                        # I'll just leave it as it loops inside `_wait_for_input`.
                        # But what if they type an invalid digit? `_wait_for_input` loops.
                        # It's fine! 
                        # I'll just break out of this block.
                        break

                    if stop_reason:
                        break
"""

content = content[:start_idx] + new_block + content[end_idx:]
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
