PLACEHOLDERS = {"NAME", "SURNAME"}


def full_name(first, last):
    """Return the student's full name in upper case, or None if TODO 1 is incomplete.

    A part counts as missing if it is not a string, is blank, or is still one
    of the scaffold placeholders.
    """
    parts = []
    for value in (first, last):
        if not isinstance(value, str):
            return None
        part = value.strip()
        if not part or part.upper() in PLACEHOLDERS:
            return None
        parts.append(part.upper())
    return " ".join(parts)


def missing_todos(name, zone, rain_topic, temp_ok):
    """Return the labels of the TODOs that are still incomplete.

    Args:
        name: Result of full_name(); None while TODO 1 is incomplete.
        zone: Zone the student monitors, e.g. "zone1".
        rain_topic: The student's MQTT topic. It must equal the zone's rain
            state topic exactly: a wildcard that happens to receive the
            messages is not accepted.
        temp_ok: True once the temperature HTTP request has succeeded.
    """
    missing = []
    if name is None:
        missing.append("TODO 1 (student name)")
    if rain_topic != f"field/{zone}/rain/state":
        missing.append("TODO 2 (MQTT topic of the rain state)")
    if not temp_ok:
        missing.append("TODO 3 (HTTP endpoint of the temperature service)")
    return missing