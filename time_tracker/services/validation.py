from __future__ import annotations


def parse_percent_to_basis_points(value: str) -> int:
    text = value.strip().replace("%", "")
    if not text:
        raise ValueError("Percent is required.")
    parts = text.split(".")
    if len(parts) > 2 or any(not part.isdigit() for part in parts if part):
        raise ValueError("Percent must be a number.")
    whole = int(parts[0] or "0")
    frac = (parts[1] if len(parts) == 2 else "")[:2].ljust(2, "0")
    basis_points = whole * 100 + int(frac or "0")
    if basis_points <= 0 or basis_points > 10000:
        raise ValueError("Percent must be greater than 0 and no more than 100.")
    return basis_points


def basis_points_to_percent(value: int) -> str:
    whole, frac = divmod(int(value), 100)
    if frac:
        return f"{whole}.{frac:02d}%"
    return f"{whole}%"


def validate_split_total(splits: list[tuple[str, int]]) -> None:
    if not splits:
        raise ValueError("At least one NWA split is required.")
    total = sum(percent for _, percent in splits)
    if total != 10000:
        raise ValueError(f"NWA splits must total exactly 100%; current total is {basis_points_to_percent(total)}.")
