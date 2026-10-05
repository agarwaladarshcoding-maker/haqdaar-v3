with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

import re

# We need to replace the block starting at `if is_box_keypad:` to the end of `elif isinstance(inp, Speech):`

# Let's just find the indices.
