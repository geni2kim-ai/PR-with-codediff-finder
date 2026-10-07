"""주문 금액 계산 모듈 (원본)."""


FREE_SHIPPING_THRESHOLD = 50000
SHIPPING_FEE = 3000


def calculate_subtotal(items):
    subtotal = 0
    for item in items:
        subtotal += item["price"] * item["quantity"]
    return subtotal


def calculate_shipping(subtotal):
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return 0
    return SHIPPING_FEE


def create_order_summary(items):
    subtotal = calculate_subtotal(items)
    shipping = calculate_shipping(subtotal)
    return {"subtotal": subtotal, "shipping": shipping, "total": subtotal + shipping}


if __name__ == "__main__":
    print(create_order_summary([{"price": 15000, "quantity": 2}]))
