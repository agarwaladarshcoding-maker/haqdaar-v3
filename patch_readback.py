with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

start_marker = """            # 2. Wait loop for this scheme's menu
            while True:
                # Set current_scheme to the scheme just read before each wait
                Engine.current_scheme = sid
                setattr(audio, "current_scheme", sid)

                rb_inp = audio.next_input(profile="readback")

                if pending_section is not None:
                    p_sid, p_sec = pending_section
                    if not (hasattr(audio, "was_cut") and audio.was_cut(f"scheme:{p_sid}:{p_sec}")):
                        sections_heard[p_sid].append(p_sec)
                    pending_section = None

                if isinstance(rb_inp, Hangup):
                    audio.hangup()
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    return False

                if isinstance(rb_inp, Silence):
                    if (hasattr(audio, "was_cut") and audio.was_cut("")) or bool(getattr(rb_inp, "cut_clip", "")):
                        replays += 1
                        if replays > tunables.READBACK_REPLAY_MAX:
                            replays = 0
                            ix += 1
                            if ix < len(named):
                                break  # Move to next scheme
                            else:
                                audio.say(("no_more_schemes",))
                                Engine.current_scheme = None
                                setattr(audio, "current_scheme", None)
                                return True
                        audio.say(("unclear_prompt", SECTION_MENU))
                        continue
                    # Normal silence on menu moves on to next scheme
                    ix += 1
                    if ix < len(named):
                        break  # Move to next scheme
                    else:
                        audio.say(("no_more_schemes",))
                        Engine.current_scheme = None
                        setattr(audio, "current_scheme", None)
                        return True
                elif isinstance(rb_inp, Digit):"""

new_block = """            # 2. Wait loop for this scheme's menu
            while True:
                # Set current_scheme to the scheme just read before each wait
                Engine.current_scheme = sid
                setattr(audio, "current_scheme", sid)

                def rb_miss_cb(m_inp, m_cnt):
                    nonlocal replays, ix
                    if isinstance(m_inp, Silence):
                        return False
                    
                    if isinstance(m_inp, Noise):
                        replays += 1
                        if replays > tunables.READBACK_REPLAY_MAX:
                            replays = 0
                            ix += 1
                            return True
                        return False
                    
                    if isinstance(m_inp, Digit):
                        replays += 1
                        if replays > tunables.READBACK_REPLAY_MAX:
                            replays = 0
                            ix += 1
                            return True
                        return False
                    return False
                    
                try:
                    rb_inp = Engine._wait_for_input(
                        audio, log, (SECTION_MENU,), profile="readback",
                        valid_keys=("1", "2", "3", "0", "*", "#"),
                        on_miss_cb=rb_miss_cb,
                        say_first=False
                    )
                except EngineDropCall as e:
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    return False

                if pending_section is not None:
                    p_sid, p_sec = pending_section
                    if not (hasattr(audio, "was_cut") and audio.was_cut(f"scheme:{p_sid}:{p_sec}")):
                        sections_heard[p_sid].append(p_sec)
                    pending_section = None

                if rb_inp is None:
                    # Breakout from miss callback (too many replays)
                    if ix < len(named):
                        break  # Move to next scheme
                    else:
                        audio.say(("no_more_schemes",))
                        Engine.current_scheme = None
                        setattr(audio, "current_scheme", None)
                        return True

                if isinstance(rb_inp, Hangup):
                    audio.hangup()
                    Engine.current_scheme = None
                    setattr(audio, "current_scheme", None)
                    return False
                
                if isinstance(rb_inp, Digit):"""

content = content.replace(start_marker, new_block)
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
