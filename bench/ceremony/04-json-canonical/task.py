import json


def main() -> None:
    value = json.loads('{"b":2,"a":1.00}')
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


main()
