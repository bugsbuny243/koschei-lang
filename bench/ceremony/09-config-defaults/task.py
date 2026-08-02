def main() -> None:
    defaults = {"port": 8080, "workers": 2}
    supplied = {"workers": 4}
    config = defaults | supplied
    print(config["port"])
    print(config["workers"])


main()
