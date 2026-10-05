with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

content = content.replace(
    'on_zero_prompts=("opener_prompt",) if box == "category" else None,\n                        on_miss_cb=handle_miss',
    'on_zero_prompts=("opener_prompt",) if box == "category" else None,\n                        on_miss_cb=handle_miss,\n                        turn_n=turn_n'
)

content = content.replace(
    'valid_keys=("1", "2", "3", "#", "*")\n                            )',
    'valid_keys=("1", "2", "3", "#", "*"),\n                                turn_n=turn_n\n                            )'
)

content = content.replace(
    'valid_keys=("1", "2", "3", "0", "*", "#"),\n                        on_miss_cb=rb_miss_cb,\n                        say_first=False\n                    )',
    'valid_keys=("1", "2", "3", "0", "*", "#"),\n                        on_miss_cb=rb_miss_cb,\n                        say_first=False,\n                        turn_n=turn_n\n                    )'
)

content = content.replace(
    'allow_speech=mode != "keypad_only" and model is not None,\n                        on_miss_cb=ae_miss_cb',
    'allow_speech=mode != "keypad_only" and model is not None,\n                        on_miss_cb=ae_miss_cb,\n                        turn_n=turn_n'
)

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
