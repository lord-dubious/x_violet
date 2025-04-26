import enum


class StrEnum(enum.Enum):
    def __str__(self):
        return self.value

    def __eq__(self, another):
        if isinstance(another, StrEnum):
            return self.value == another.value
        return self.value == str(another)
