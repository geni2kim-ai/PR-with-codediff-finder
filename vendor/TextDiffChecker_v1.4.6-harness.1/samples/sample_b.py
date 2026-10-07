import os


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    return data


def recieve_data(path):
    raw = load_config(path)
    return raw


def calculate_totla(items):
    total = 0
    for item in items:
        total += item
    return total


MAX_RETRY = 5
RETRY_DELAY = 10  # TODO: 지수 백오프로 변경

element = document.getElementByID("main")
console.log("debug output", element)
pritn("done")
if (MAX_RETRY == 5):
    print("max retry reached")
