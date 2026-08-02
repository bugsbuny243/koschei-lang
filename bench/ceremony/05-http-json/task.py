import json
import urllib.request


def main() -> None:
    with urllib.request.urlopen("https://api.example.com/data") as response:
        value = json.load(response)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


main()
