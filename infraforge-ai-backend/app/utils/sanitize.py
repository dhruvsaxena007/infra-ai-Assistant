def without_embedding(machine: dict) -> dict:
    """Copy a machine document without the embedding field for API responses."""
    if not machine:
        return {}
    return {k: v for k, v in machine.items() if k != "embedding"}


def without_embeddings(machines: list) -> list:
    return [without_embedding(m) for m in (machines or [])]


def _dedupe_key(machine: dict):
    """
    Content key used to detect duplicate listings.

    Works on normalized machines (id/name/category/city/model/price_per_day).
    """
    return (
        str(machine.get("id") or machine.get("_id", "")).strip().lower(),
        str(machine.get("name", "")).strip().lower(),
        str(machine.get("category", "")).strip().lower(),
        str(machine.get("city", "")).strip().lower(),
        str(machine.get("model", "")).strip().lower(),
        machine.get("price_per_day"),
    )


def deduplicate_machines(machines: list) -> list:
    """
    Remove duplicate machines from a result list.

    A machine is skipped if its _id was already seen OR its content key
    (name + category + city + model + price_per_day) was already seen. This
    handles both "same document returned twice" and "same listing inserted
    multiple times under different _id" cases, so the UI never shows the same
    machine repeated. Order is preserved.
    """
    seen_ids: set = set()
    seen_keys: set = set()
    out: list = []

    for machine in machines or []:
        if not isinstance(machine, dict):
            continue

        raw_id = machine.get("_id")
        machine_id = str(raw_id) if raw_id is not None else None
        key = _dedupe_key(machine)

        if (machine_id and machine_id in seen_ids) or key in seen_keys:
            continue

        if machine_id:
            seen_ids.add(machine_id)
        seen_keys.add(key)
        out.append(machine)

    return out
