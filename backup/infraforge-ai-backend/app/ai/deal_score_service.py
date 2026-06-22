from app.utils.machine_normalizer import effective_price, rating_score_neutral


def calculate_deal_score(machine, average_market_price):
    current_price = effective_price(machine)
    rating = machine.get("rating")
    listing_type = str(machine.get("listing_type") or "rent").lower()
    specs = machine.get("specifications") or {}

    if current_price is None or average_market_price is None:
        return {
            "machine_name": machine.get("name"),
            "deal_score": None,
            "deal_label": "Not Enough Data",
            "reason": "Price or market average is missing.",
        }

    score = 50

    if current_price < average_market_price:
        score += 25
    elif current_price == average_market_price:
        score += 15
    else:
        score -= 15

    if rating is not None:
        if rating >= 4.5:
            score += 20
        elif rating >= 4.0:
            score += 12
        elif rating >= 3.5:
            score += 5
        else:
            score -= 8
    else:
        score += 5

    if machine.get("availability"):
        score += 8
    else:
        score -= 10

    condition = str(specs.get("condition") or "").lower()
    if condition == "used":
        score += 2
    elif condition == "new":
        score += 5

    deposit = machine.get("security_deposit")
    if listing_type == "rent" and deposit is not None and deposit <= 500:
        score += 3

    score = max(0, min(100, score))

    if score >= 85:
        label = "Excellent Deal"
    elif score >= 70:
        label = "Good Deal"
    elif score >= 50:
        label = "Average Deal"
    else:
        label = "Poor Deal"

    rating_note = (
        f"Rating {rating}/5 considered."
        if rating is not None
        else "Rating not available — neutral score used."
    )

    return {
        "machine_name": machine.get("name"),
        "listing_type": listing_type,
        "deal_score": score,
        "deal_label": label,
        "reason": (
            "Deal score uses price vs market, availability, condition, deposit, "
            f"and rating when present. {rating_note}"
        ),
    }
