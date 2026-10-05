with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

old_confirm = """
                    confirm_repeats = 0
                    while True:
                        confirm_inp = audio.next_input(profile="confirm")
                        if isinstance(confirm_inp, Digit):
"""
new_confirm = """
                    confirm_repeats = 0
                    while True:
                        try:
                            confirm_inp = Engine._wait_for_input(
                                audio, log, (), profile="confirm",
                                valid_keys=("1", "2", "3", "#", "*")
                            )
                        except EngineDropCall as e:
                            survs_s = Filter.survivors(box_vector, corpus)
                            silence_stop = (STOP_ZERO_SURVIVORS if len(survs_s) == 0 else (STOP_LE_4_SURVIVORS if len(survs_s) <= tunables.STOP_SURVIVORS else STOP_NO_SPLIT))
                            log.close(reason=silence_stop, ladder_rung=e.ladder_rung, mode=mode)
                            return
                        if isinstance(confirm_inp, Digit):
"""
content = content.replace(old_confirm, new_confirm)

# Note: _wait_for_input internally does `audio.say(prompts)`. But here `prompts` is `()`. 
# Wait, the confirmation prompt is said BEFORE the while loop!
# Wait, if `_wait_for_input` takes `()`, on miss it will say `("unclear_prompt",) + ()` which is just `unclear_prompt`, but it WON'T repeat the confirmation question!
