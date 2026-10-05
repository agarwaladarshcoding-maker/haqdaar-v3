with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

import re

# We want to replace the block starting at `if is_box_keypad:` to the end of `elif isinstance(inp, Speech):` (but wait, what about the rest?)
# I'll just write a script that finds the start and end and replaces it.

start_marker = "                if is_box_keypad:\n                    if box == \"category\":"
end_marker = "                    # --- Voice mode: process spoken answer via model ---"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Could not find markers")
    exit(1)

new_block = """                if is_box_keypad:
                    if box == "category":
                        prompt_ids = ("opener_short_prompt",)
                    elif box == "state":
                        prompt_ids = ("state_q_maharashtra",)
                    else:
                        prompt_ids = (f"keypad_{box}",)
                else:
                    if box == "category":
                        prompt_ids = ("opener_short_prompt",)
                    elif box == "state":
                        prompt_ids = ("state_q_maharashtra",)
                    elif box_strikes[box] == 1:
                        prompt_ids = (f"rephrase_{box}",)
                    else:
                        prompt_ids = (f"q_{box}",)

                def handle_miss(m_inp, miss_count):
                    nonlocal turn_n, silence_ladder, mode, stop_reason, question_count
                    if isinstance(m_inp, Silence):
                        return False
                    
                    if isinstance(m_inp, Noise):
                        turn_n += 1
                        silence_ladder = 0
                        box_strikes[box] += 1
                        log.write(TurnLogRecord(turn_n=turn_n, turn_class="NOISE"))
                        if mode != "keypad_only" and (getattr(audio, "keypad_only", False) or getattr(getattr(audio, "turn", None), "keypad_only", False) or getattr(model, "keypad_only", False)):
                            mode = "keypad_only"
                            log.write({"mode": "keypad_only"})
                            audio.say(("keypad_only_mode",))
                            if turn_n >= tunables.MAX_TURNS:
                                stop_reason = STOP_MAX_TURNS
                            return True
                        if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
                            if mode == "keypad_only" or is_box_keypad:
                                box_vector[box] = UNKNOWN
                                question_count += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="ANSWER", box=box, value=UNKNOWN, unknown_source="keypad_dropped"))
                                return True
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            return True
                        return False

                    if isinstance(m_inp, Digit):
                        turn_n += 1
                        box_strikes[box] += 1
                        log.write(TurnLogRecord(turn_n=turn_n, turn_class="UNCLEAR", transcript=str(m_inp.digit)))
                        if getattr(audio, "keypad_only", False) or getattr(getattr(audio, "turn", None), "keypad_only", False):
                            mode = "keypad_only"
                            log.write({"mode": "keypad_only"})
                            audio.say(("keypad_only_mode",))
                        if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
                            if mode == "keypad_only" or is_box_keypad:
                                box_vector[box] = UNKNOWN
                                question_count += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="ANSWER", box=box, value=UNKNOWN, unknown_source="keypad_dropped"))
                                return True
                        if turn_n >= tunables.MAX_TURNS:
                            stop_reason = STOP_MAX_TURNS
                            return True
                        return False
                        
                    if isinstance(m_inp, Speech):
                        if is_box_keypad or model is None:
                            turn_n += 1
                            box_strikes[box] += 1
                            log.write(TurnLogRecord(turn_n=turn_n, turn_class="UNCLEAR", discarded_transcript=getattr(m_inp, "text", "")))
                            if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
                                box_vector[box] = UNKNOWN
                                question_count += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="ANSWER", box=box, value=UNKNOWN, unknown_source="keypad_dropped"))
                                return True
                            if turn_n >= tunables.MAX_TURNS:
                                stop_reason = STOP_MAX_TURNS
                                return True
                        return False
                    return False

                valid_keys = tuple([str(i) for i in range(1, len(corpus.values(box)) + 1)] + ["*", "#", "0"])
                try:
                    inp = Engine._wait_for_input(
                        audio, log, prompt_ids, profile="normal" if is_box_keypad else "spoken",
                        valid_keys=valid_keys,
                        allow_speech=not is_box_keypad and model is not None,
                        miss_threshold=2 if box == "category" else None,
                        on_miss_prompts=("opener_prompt",) if box == "category" else None,
                        on_zero_prompts=("opener_prompt",) if box == "category" else None,
                        on_miss_cb=handle_miss
                    )
                except EngineDropCall as e:
                    survs_s = Filter.survivors(box_vector, corpus)
                    silence_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                    log.close(reason=silence_stop, ladder_rung=e.ladder_rung, mode=mode)
                    return
                
                if inp is None:
                    if stop_reason: break
                    continue

                if isinstance(inp, Hangup):
                    audio.hangup()
                    survs_s = Filter.survivors(box_vector, corpus)
                    h_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                    log.close(reason=h_stop, ladder_rung=0, mode=mode)
                    return

                if isinstance(inp, Digit):
                    silence_ladder = 0
                    turn_n, question_count, stop_reason, act = Engine._handle_digit_input(
                        audio, log, corpus, box, inp, box_vector, box_strikes, turn_n, question_count, mode, is_box_keypad
                    )
                    if stop_reason: break
                    continue
                
                if isinstance(inp, Speech):
                    silence_ladder = 0
                    transcript = getattr(inp, "text", "") or ""
"""

content = content[:start_idx] + new_block + content[end_idx:]
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
