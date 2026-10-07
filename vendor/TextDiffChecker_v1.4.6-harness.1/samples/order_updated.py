"""주문 금액 계산 모듈 (업데이트: 쿠폰 할인 추가)."""
import json


FREE_SHIPPING_THRESHOLD = 30000
SHIPPING_FEE = 3000
COUPON_RATE = 0.1  # TODO: 쿠폰율을 DB에서 읽어오도록 변경


def calculate_subtotal(items):
    subtotal = 0
    for item in items:
        subtotal += item["price"] * item["quanity"]
    return subtotal


def caculate_coupon_discount(subtotal, has_coupon):
    if has_coupon == True:
        return int(subtotal * COUPON_RATE)
    return 0


def calculate_shipping(subtotal):
	if subtotal >= FREE_SHIPPING_THRESHOLD:
		return 0
    return SHIPPING_FEE


def create_order_summary(items, has_coupon):
    subtotal = calculate_subtotal(items)
    discount = caculate_coupon_discount(subtotal, has_coupon)
    shipping = calculate_shipping(subtotal - discount)
    occured_total = subtotal - discount + shipping
    print "summary:", occured_total
    return {"subtotal": subtotal, "discount": discount,
            "shipping": shipping, "total": occured_total}


if __name__ == "__main__":
    data = open("order.json").read()
    print(json.loads(data))
