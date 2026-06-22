from app.ai.insight_helpers import average_peer_price, filter_priced_peers
from app.utils.machine_normalizer import effective_price, format_price_label


def _peer_price(machine: dict):
    return effective_price(machine)


def calculate_price_insight(machine, similar_machines):
    listing_type = str(machine.get("listing_type") or "rent").lower()
    current_price = _peer_price(machine)
    price_label = "price_per_day" if listing_type == "rent" else "selling_price"

    if not similar_machines:
        return {
            "machine_name": machine.get("name"),
            "listing_type": listing_type,
            "current_price": current_price,
            "average_market_price": None,
            "price_status": "Not Enough Data",
            "recommendation": "Not enough similar machines available for price comparison.",
        }

    priced_peers = filter_priced_peers(similar_machines)
    average_price, count = average_peer_price(priced_peers)

    if count == 0:
        return {
            "machine_name": machine.get("name"),
            "listing_type": listing_type,
            "current_price": current_price,
            "average_market_price": None,
            "price_status": "Not Enough Data",
            "recommendation": "Similar machines do not have valid pricing data.",
        }

    if current_price is None:
        return {
            "machine_name": machine.get("name"),
            "listing_type": listing_type,
            "current_price": None,
            "average_market_price": round(average_price, 2),
            "price_status": "Invalid Price",
            "recommendation": "This machine does not have a valid price.",
        }

    price_difference = current_price - average_price
    percentage_difference = (price_difference / average_price) * 100 if average_price else 0

    if percentage_difference <= -10:
        price_status = "Below Market Price"
        recommendation = (
            "This listing looks budget-friendly compared to similar machines."
        )
    elif percentage_difference >= 10:
        price_status = "Above Market"
        recommendation = (
            "This listing is priced higher than similar machines. Compare "
            "condition, year, availability, and location before deciding."
        )
    else:
        price_status = "Fair Market Price"
        recommendation = "This listing price is close to the market average."

    return {
        "machine_name": machine.get("name"),
        "category": machine.get("category_display") or machine.get("category"),
        "city": machine.get("city"),
        "listing_type": listing_type,
        "rent_type": machine.get("rent_type"),
        "current_price": current_price,
        "average_market_price": round(average_price, 2),
        "price_difference": round(price_difference, 2),
        "percentage_difference": round(percentage_difference, 2),
        "price_status": price_status,
        "recommendation": recommendation,
        "similar_machine_count": count,
        "price_field": price_label,
    }
