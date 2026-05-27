from enum import Enum


class JobType(str, Enum):
    COMPILE = "compile"
    EVAL = "eval"

    def __str__(self) -> str:
        return str(self.value)
