def main() -> None:
    left = ["alpha", "beta", "gamma"]
    right = ["alpha", "BETA", "gamma"]
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            print(f"difference at {index}")
            break


main()
