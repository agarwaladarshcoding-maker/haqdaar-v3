with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

start_marker = """            # --- 7. Anything Else ---
            ae_strikes = 0
            while True:
                audio.say(("anything_else",))
                if mode == "keypad_only":
                    ae_inp = audio.next_input(profile="normal")
                else:
                    ae_inp = audio.next_input(profile="confirm")"""

end_marker = """                else:
                    break"""

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx) + len(end_marker)

if start_idx == -1 or end_idx == -1:
    print("Could not find markers")
    print(start_idx, end_idx)
    exit(1)

new_block = """            # --- 7. Anything Else ---
            ae_strikes = 0
            while True:
                def ae_miss_cb(m_inp, m_cnt):
                    nonlocal turn_n, mode, ae_strikes
                    if isinstance(m_inp, Silence):
                        return False
                    if isinstance(m_inp, Noise):
                        ae_strikes += 1
                        if ae_strikes >= tunables.BOX_STRIKES_TO_KEYPAD:
                            return True
                        return False
                    if isinstance(m_inp, Digit):
                        if m_inp.digit == "#":
                            audio.repeat()
                            return False
                        ae_strikes += 1
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(getattr(m_inp, "prompt_n", -1), "anything_else", "key", str(m_inp.digit), False, "not_on_menu")
                        if ae_strikes >= tunables.BOX_STRIKES_TO_KEYPAD:
                            return True
                        return False
                    return False
                    
                try:
                    ae_inp = Engine._wait_for_input(
                        audio, log, ("anything_else",), profile="normal" if mode == "keypad_only" else "confirm",
                        valid_keys=("1", "2", "0", "*", "#"),
                        allow_speech=mode != "keypad_only" and model is not None,
                        on_miss_cb=ae_miss_cb
                    )
                except EngineDropCall as e:
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS, ladder_rung=e.ladder_rung, mode=mode)
                    return
                
                if ae_inp is None:
                    # Breakout due to strikes
                    break

                if isinstance(ae_inp, Hangup):
                    audio.hangup()
                    log.close(reason=STOP_ZERO_SURVIVORS if not survs else STOP_LE_4_SURVIVORS, ladder_rung=ladder_rung, mode=mode)
                    return
                is_yes = False
                if isinstance(ae_inp, Digit):
                    if ae_inp.digit == "*":
                        curr_lang = getattr(audio, "language", "hi")
                        new_lang = _next_lang(curr_lang)
                        if hasattr(audio, "language"):
                            audio.language = new_lang
                        log.write(LangSwitchRecord(lang=new_lang, lang_source="keypad", turn_n=turn_n))
                        continue
                    elif ae_inp.digit == "1":
                        is_yes = True
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(getattr(ae_inp, "prompt_n", -1), "anything_else", "key", "1", True, "ok")
                        break
                    elif ae_inp.digit in ("0", "2"):
                        is_yes = False
                        if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                            audio.trace.input_event(getattr(ae_inp, "prompt_n", -1), "anything_else", "key", str(ae_inp.digit), True, "ok")
                        break
                elif isinstance(ae_inp, Speech):
                    spk = str(getattr(ae_inp, "text", "") or "").strip().lower()
                    if model is not None and hasattr(model, "confirm"):
                        confirmed = model.confirm(spk, lang=getattr(audio, "language", None))
                    else:
                        confirmed = None
                    if confirmed is None and Engine._try_question(
                        audio, model, corpus, log, qa, ae_inp, mode, turn_n, box_vector, asked="anything_else",
                    ):
                        continue  # the loop asks anything-else again
                    if confirmed is True:
                        is_yes = True
                    break
                else:
                    break"""

content = content[:start_idx] + new_block + content[end_idx:]
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
