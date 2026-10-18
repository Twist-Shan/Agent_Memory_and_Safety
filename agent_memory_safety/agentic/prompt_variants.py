"""Explicit filesystem prompt conditions; upstream files remain unmodified."""

FS_PROMPT_VARIANTS = ("original", "no-memory-claims")
MEMORY_CLAIM = (
    "It already contains a scratchpad (`scratchpad.md`) and summaries of previous matches "
    "in `/home/user/past_games/`. "
)


def configure_fs_prompt(env, variant="original"):
    if variant not in FS_PROMPT_VARIANTS:
        raise ValueError(f"Unknown filesystem prompt variant: {variant}")
    if variant == "original":
        return env
    original = env.get_fs_system_prompt()
    if original.count(MEMORY_CLAIM) != 1:
        raise ValueError("Upstream filesystem prompt changed")
    prompt = original.replace(MEMORY_CLAIM, "", 1)
    env.get_fs_system_prompt = lambda: prompt
    return env
