def buggy_sort(values: list[int]) -> list[int]:
    """Return values in ascending order while preserving duplicates."""
    return sorted(set(values))  # seeded bug: duplicates are discarded


def buggy_absolute(value: int) -> int:
    """Return the non-negative magnitude of value."""
    if value < 0:
        return value  # seeded bug: should negate the value
    return value


def correct_sort(values: list[int]) -> list[int]:
    return sorted(values)

