with open("haqdaar/engine/call.py", "r") as f:
    content = f.read()

old_wait = """    @staticmethod
    def _wait_for_input(
        audio: Any, log: Any, prompts: tuple[str, ...], profile: str,
        valid_keys: tuple[str, ...] | None = None, allow_speech: bool = False,
        miss_threshold: int | None = None, on_miss_prompts: tuple[str, ...] | None = None,
        on_zero_prompts: tuple[str, ...] | None = None, on_miss_cb: Any = None
    ) -> Any:
        audio.say(prompts)"""

new_wait = """    @staticmethod
    def _wait_for_input(
        audio: Any, log: Any, prompts: tuple[str, ...], profile: str,
        valid_keys: tuple[str, ...] | None = None, allow_speech: bool = False,
        miss_threshold: int | None = None, on_miss_prompts: tuple[str, ...] | None = None,
        on_zero_prompts: tuple[str, ...] | None = None, on_miss_cb: Any = None,
        say_first: bool = True
    ) -> Any:
        if say_first:
            audio.say(prompts)"""

content = content.replace(old_wait, new_wait)
with open("haqdaar/engine/call.py", "w") as f:
    f.write(content)
