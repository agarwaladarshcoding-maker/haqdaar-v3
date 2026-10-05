with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

old_turn0 = """
        if hasattr(audio, "select_language"):
            lang, lang_source = audio.select_language()
        else:
            audio.say(("greeting_trilingual",))
            inp = audio.next_input(profile="turn0")
            if isinstance(inp, Hangup):
                audio.hangup()
                log.close(reason=STOP_ZERO_SURVIVORS, ladder_rung=0, mode="voice")
                return
            elif isinstance(inp, Digit):
                if inp.digit in tunables.turn0_keys():
                    lang, lang_source = tunables.turn0_keys()[inp.digit], "keypad"
                else:
                    lang, lang_source = "hi", "default"
            else:
                lang, lang_source = "hi", "default"
"""

new_turn0 = """
        if hasattr(audio, "select_language"):
            lang, lang_source = audio.select_language()
        else:
            try:
                inp = Engine._wait_for_input(
                    audio, log, ("greeting_trilingual",), "turn0",
                    valid_keys=tuple(tunables.turn0_keys().keys()),
                    allow_speech=False
                )
                if isinstance(inp, Hangup):
                    audio.hangup()
                    log.close(reason=STOP_ZERO_SURVIVORS, ladder_rung=0, mode="voice")
                    return
                lang, lang_source = tunables.turn0_keys()[inp.digit], "keypad"
            except EngineDropCall as e:
                log.close(reason=STOP_ZERO_SURVIVORS, ladder_rung=e.ladder_rung, mode="voice")
                return
"""

content = content.replace(old_turn0, new_turn0)
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)

