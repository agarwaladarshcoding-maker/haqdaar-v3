with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

import re

# Update signature
content = content.replace(
    "on_zero_prompts: tuple[str, ...] | None = None, on_miss_cb: Any = None,",
    "on_zero_prompts: tuple[str, ...] | None = None, on_miss_cb: Any = None,\n        turn_n: int = 0,"
)

# Update log.write(TurnLogRecord(...))
content = content.replace(
    'log.write(TurnLogRecord(turn_n=getattr(audio, "turn_n", 0), turn_class="SILENCE", silence_n=ladder_rung))',
    'log.write(TurnLogRecord(turn_n=turn_n, turn_class="SILENCE", silence_n=ladder_rung))'
)
content = content.replace(
    'log.write(TurnLogRecord(turn_n=getattr(audio, "turn_n", 0), turn_class="NOISE"))',
    'log.write(TurnLogRecord(turn_n=turn_n, turn_class="NOISE"))'
)

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
