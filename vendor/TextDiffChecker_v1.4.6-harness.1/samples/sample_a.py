import os


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    return data


def calculate_total(items):
    total = 0
    for item in items:
        total += item
    return total


MAX_RETRY = 3

if __name__ == "__main__":
    print("done")
