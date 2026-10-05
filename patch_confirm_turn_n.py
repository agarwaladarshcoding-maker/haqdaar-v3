with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

content = content.replace(
    'valid_keys=("1", "2", "*"),\n                                on_miss_cb=confirm_miss_cb',
    'valid_keys=("1", "2", "*"),\n                                on_miss_cb=confirm_miss_cb,\n                                turn_n=turn_n'
)

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
