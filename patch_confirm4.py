with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

start_marker = """                    audio.say(confirm_seq)

                    # Confirmation loop: bounded against repeat-mashing via confirm_repeats
                    # without consuming cap turns (# and SILENCE do not consume turns per T14/T16)
                    confirm_repeats = 0
                    while True:
                        confirm_inp = audio.next_input(profile="confirm")"""

end_marker = """                    if stop_reason:
                        break"""

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Could not find markers")
    print(start_idx, end_idx)
    exit(1)

new_block = """                    # Confirmation loop: bounded against repeat-mashing via confirm_repeats
                    # without consuming cap turns (# and SILENCE do not consume turns per T14/T16)
                    confirm_repeats = 0
                    while True:
                        def confirm_miss_cb(m_inp, m_cnt):
                            nonlocal turn_n, box_strikes, stop_reason, mode, silence_ladder
                            if isinstance(m_inp, Silence):
                                return False
                            if isinstance(m_inp, Noise):
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="NOISE"))
                                if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
                                    if mode != "keypad_only" and (getattr(audio, "keypad_only", False) or getattr(model, "keypad_only", False)):
                                        mode = "keypad_only"
                                        audio.say(("keypad_only_mode",))
                                    return True
                                return False
                            if isinstance(m_inp, Digit):
                                if m_inp.digit == "#":
                                    audio.repeat()
                                    return False
                                turn_n += 1
                                box_strikes[box] += 1
                                log.write(TurnLogRecord(turn_n=turn_n, turn_class="UNCLEAR", transcript=str(m_inp.digit)))
                                if box_strikes[box] >= tunables.BOX_STRIKES_TO_KEYPAD:
                                    if mode != "keypad_only" and (getattr(audio, "keypad_only", False) or getattr(model, "keypad_only", False)):
                                        mode = "keypad_only"
                                        audio.say(("keypad_only_mode",))
                                    return True
                                return False
                            return False

                        try:
                            confirm_inp = Engine._wait_for_input(
                                audio, log, confirm_seq, profile="confirm",
                                valid_keys=("1", "2", "*"),
                                on_miss_cb=confirm_miss_cb
                            )
                        except EngineDropCall as e:
                            survs_s = Filter.survivors(box_vector, corpus)
                            silence_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                            log.close(reason=silence_stop, ladder_rung=e.ladder_rung, mode=mode)
                            return

                        if confirm_inp is None:
                            # Breakout from miss cb due to strikes
                            break
                        
                        if isinstance(confirm_inp, Hangup):
                            audio.hangup()
                            survs_s = Filter.survivors(box_vector, corpus)
                            h_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                            log.close(reason=h_stop, ladder_rung=ladder_rung, mode=mode)
                            return
                        
                        if isinstance(confirm_inp, Digit):
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
                        break

                    if stop_reason:
                        break"""

content = content[:start_idx] + new_block + content[end_idx:]
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
