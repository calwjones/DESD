from decimal import Decimal, ROUND_HALF_UP


COMMISSION_RATE = Decimal("0.05")
PRODUCER_RATE = Decimal("1") - COMMISSION_RATE


def _q(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_commission_split(order):
    """
    Compute the 5%/95% split for an order, broken down per producer.

    Returns a dict:
        {
            "total_gross": Decimal,
            "total_commission": Decimal,
            "total_net": Decimal,
            "splits": [
                {"producer": User, "gross": Decimal, "commission": Decimal, "net": Decimal},
                ...
            ],
        }

    Multi-vendor orders contain one entry per producer, with each producer's
    portion calculated from their own item subtotals (TC-025).
    """
    items = order.items.select_related("product__producer").all()

    by_producer = {}
    for item in items:
        producer = item.product.producer
        subtotal = Decimal(item.price) * item.quantity
        by_producer.setdefault(producer.id, {"producer": producer, "gross": Decimal("0")})
        by_producer[producer.id]["gross"] += subtotal

    splits = []
    for entry in by_producer.values():
        gross = _q(entry["gross"])
        commission = _q(gross * COMMISSION_RATE)
        net = _q(gross * PRODUCER_RATE)
        splits.append({
            "producer": entry["producer"],
            "gross": gross,
            "commission": commission,
            "net": net,
        })

    total_gross = _q(Decimal(order.total))
    total_commission = _q(total_gross * COMMISSION_RATE)
    total_net = _q(total_gross * PRODUCER_RATE)

    return {
        "total_gross": total_gross,
        "total_commission": total_commission,
        "total_net": total_net,
        "splits": splits,
    }
