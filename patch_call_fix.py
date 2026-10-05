import re

with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

# Replace the specific line in _wait_for_input
content = content.replace(
    'if inp.digit == "0" and on_zero_prompts is not None:',
    'if inp.digit == "0" and on_zero_prompts is not None and current_prompts != on_zero_prompts:'
)

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
