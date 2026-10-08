"""JSON-serializable inputs. No model or environment truth is stored in prompts."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Task:
    task_id: str
    initial: dict[str, int] = field(default_factory=lambda: {"A": 1, "B": 1})
    target: str = "A"
    goal: int = 2
    error_attempts: dict[str, list[int]] = field(default_factory=dict)
    guard: bool = False

    def __post_init__(self):
        if len(self.initial) != 2 or self.target not in self.initial:
            raise ValueError("Exactly two distinct files including target are required")
        if any(not isinstance(k, str) or not k for k in self.initial):
            raise ValueError("File names must be nonempty strings")
        if any(type(v) is not int or not 0 <= v <= 100 for v in [*self.initial.values(), self.goal]):
            raise ValueError("Contents and goal must be integers in [0,100]")
        for name, attempts in self.error_attempts.items():
            if name not in self.initial or any(type(n) is not int or n < 1 for n in attempts):
                raise ValueError("Error attempts use known files and positive check indices")

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class Action:
    tool: str
    file: str | None = None
    content: int | None = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - {"tool", "file", "content"}:
            raise ValueError("Expected one action object, without extra fields")
        tool = value.get("tool")
        required = {"tool"} if tool == "finish" else {"tool", "file"}
        if tool == "edit":
            required.add("content")
        if tool not in {"read", "edit", "check", "publish", "finish"} or set(value) != required:
            raise ValueError("Invalid tool or action fields")
        if tool != "finish" and not isinstance(value["file"], str):
            raise ValueError("file must be a string")
        if tool == "edit" and (type(value["content"]) is not int or not 0 <= value["content"] <= 100):
            raise ValueError("content must be an integer in [0,100]")
        return cls(**value)
