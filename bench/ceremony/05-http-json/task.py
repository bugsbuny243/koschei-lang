import urllib.request


def main() -> None:
    with urllib.request.urlopen("https://api.example.com/data") as response:
        print(response.read().decode("utf-8"))


main()
