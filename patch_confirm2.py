with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

old_confirm = """
                    # --- Confirmation Turn: Mouth reads back what it heard ---
                    confirm_seq = (
                        "bundle_confirm_intro",
                        f"chip_{box}_{proposed_val}",
                        "confirm_yn_suffix",
                    )
                    audio.say(confirm_seq)

                    # Confirmation loop: bounded against repeat-mashing via confirm_repeats
                    # without consuming cap turns (# and SILENCE do not consume turns per T14/T16)
                    confirm_repeats = 0
                    while True:
                        try:
                            confirm_inp = Engine._wait_for_input(
                                audio, log, (), profile="confirm",
                                valid_keys=("1", "2", "3", "#", "*")
                            )
"""
new_confirm = """
                    # --- Confirmation Turn: Mouth reads back what it heard ---
                    confirm_seq = (
                        "bundle_confirm_intro",
                        f"chip_{box}_{proposed_val}",
                        "confirm_yn_suffix",
                    )
                    # Confirmation loop: bounded against repeat-mashing via confirm_repeats
                    # without consuming cap turns (# and SILENCE do not consume turns per T14/T16)
                    confirm_repeats = 0
                    while True:
                        try:
                            confirm_inp = Engine._wait_for_input(
                                audio, log, confirm_seq, profile="confirm",
                                valid_keys=("1", "2", "3", "#", "*")
                            )
"""
content = content.replace(old_confirm, new_confirm)
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
