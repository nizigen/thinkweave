"""Version compatibility checks for TEA protocol envelopes."""

from __future__ import annotations


def parse_schema_version(version: str) -> tuple[int, int]:
    raw = str(version or "").strip()
    if not raw:
        raise ValueError("missing schema version")
    parts = raw.split(".")
    if len(parts) != 2:
        raise ValueError(f"invalid schema version format: {raw!r}")
    try:
        major = int(parts[0])
        minor = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"invalid schema version format: {raw!r}") from exc
    if major < 0 or minor < 0:
        raise ValueError(f"invalid schema version format: {raw!r}")
    return major, minor


def check_compatibility(
    incoming_version: str,
    supported_version: str,
) -> tuple[bool, str]:
    try:
        incoming_major, incoming_minor = parse_schema_version(incoming_version)
    except ValueError as exc:
        return False, str(exc)

    try:
        supported_major, supported_minor = parse_schema_version(supported_version)
    except ValueError as exc:
        return False, str(exc)

    if incoming_major != supported_major:
        return False, (
            "incompatible major version: "
            f"incoming={incoming_major}, supported={supported_major}"
        )
    if incoming_minor > supported_minor:
        return False, (
            "incoming minor version is newer than supported: "
            f"incoming={incoming_minor}, supported={supported_minor}"
        )
    return True, "ok"

