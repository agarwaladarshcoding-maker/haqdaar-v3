import re

with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

helper = """
class EngineDropCall(Exception):
    def __init__(self, ladder_rung):
        self.ladder_rung = ladder_rung

class Engine:
    \"\"\"Stateful orchestrator for a single phone call.\"\"\"
    current_scheme: str | None = None

    @staticmethod
    def _wait_for_input(
        audio: Any, log: Any, prompts: tuple[str, ...], profile: str,
        valid_keys: tuple[str, ...] | None = None, allow_speech: bool = False,
        miss_threshold: int | None = None, on_miss_prompts: tuple[str, ...] | None = None,
        on_zero_prompts: tuple[str, ...] | None = None, on_miss_cb: Any = None
    ) -> Any:
        audio.say(prompts)
        miss_count = 0
        ladder_rung = 0
        current_prompts = prompts

        while True:
            inp = audio.next_input(profile=profile)
            if isinstance(inp, Hangup):
                return inp
            
            is_miss = False
            if isinstance(inp, Silence):
                is_cut = (hasattr(audio, "was_cut") and audio.was_cut("")) or bool(getattr(inp, "cut_clip", ""))
                if not is_cut:
                    ladder_rung = inp.n if (hasattr(inp, "n") and inp.n) else (ladder_rung + 1)
                    log.write(TurnLogRecord(turn_n=getattr(audio, "turn_n", 0), turn_class="SILENCE", silence_n=ladder_rung))
                    miss_count += 1
                    if on_miss_cb:
                        if on_miss_cb(inp, miss_count): return None
                    
                    next_p = on_miss_prompts if (miss_threshold and miss_count >= miss_threshold) else prompts
                    if ladder_rung == 1:
                        current_prompts = ("did_not_get_reply",) + next_p
                        audio.say(current_prompts)
                        continue
                    elif ladder_rung == 2:
                        current_prompts = ("silence_presence",)
                        audio.say(current_prompts)
                        continue
                    else:
                        audio.say(("closing_farewell",))
                        if hasattr(audio, "on_mark"): audio.on_mark("closing_farewell")
                        audio.hangup()
                        raise EngineDropCall(ladder_rung)
                else:
                    is_miss = True
            elif isinstance(inp, Noise):
                is_miss = True
            elif isinstance(inp, Digit):
                if inp.digit == "0" and on_zero_prompts is not None:
                    miss_count = 0
                    ladder_rung = 0
                    current_prompts = on_zero_prompts
                    audio.say(current_prompts)
                    continue
                if valid_keys is not None and inp.digit not in valid_keys:
                    is_miss = True
                    if hasattr(audio, "trace") and getattr(audio, "trace", None) is not None:
                        audio.trace.input_event(prompt_n=getattr(inp, "prompt_n", -1), prompt=profile, event="key", value=str(inp.digit), took=False, why="not_on_menu")
                else:
                    return inp
            elif isinstance(inp, Speech):
                if not allow_speech:
                    is_miss = True
                else:
                    return inp
            else:
                return inp

            if is_miss:
                if isinstance(inp, Noise):
                    log.write(TurnLogRecord(turn_n=getattr(audio, "turn_n", 0), turn_class="NOISE"))
                miss_count += 1
                ladder_rung = 0
                if on_miss_cb:
                    if on_miss_cb(inp, miss_count): return None
                next_p = on_miss_prompts if (miss_threshold and miss_count >= miss_threshold) else prompts
                current_prompts = ("unclear_prompt",) + next_p
                audio.say(current_prompts)
"""

content = content.replace("""class Engine:
    \"\"\"Stateful orchestrator for a single phone call.\"\"\"
    current_scheme: str | None = None""", helper)

with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)

