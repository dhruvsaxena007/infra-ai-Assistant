from app.utils.machine_normalizer import effective_price, rating_score_neutral


def compare_machines(machine1, machine2):
    comparison = {}

    price1 = effective_price(machine1) or 0
    price2 = effective_price(machine2) or 0
    rating1 = rating_score_neutral(machine1)
    rating2 = rating_score_neutral(machine2)

    if price1 < price2:
        comparison["better_for_budget"] = machine1.get("name", "Machine 1")
    else:
        comparison["better_for_budget"] = machine2.get("name", "Machine 2")

    if (machine1.get("rating") or 0) > (machine2.get("rating") or 0):
        comparison["better_rating"] = machine1.get("name", "Machine 1")
    elif (machine2.get("rating") or 0) > (machine1.get("rating") or 0):
        comparison["better_rating"] = machine2.get("name", "Machine 2")
    else:
        comparison["better_rating"] = "Similar — rating not available or equal"

    score1 = rating1 * 0.5 + (1 if machine1.get("availability") else 0) * 0.2 - price1 * 0.00005
    score2 = rating2 * 0.5 + (1 if machine2.get("availability") else 0) * 0.2 - price2 * 0.00005

    comparison["overall_recommendation"] = (
        machine1.get("name", "Machine 1")
        if score1 >= score2
        else machine2.get("name", "Machine 2")
    )
    comparison["machine_1"] = machine1
    comparison["machine_2"] = machine2
    return comparison
