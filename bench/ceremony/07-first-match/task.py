def main() -> None:
    found = None
    for value in [1, 3, 6, 8]:
        if value % 2 == 0:
            found = value
            break
    print(found if found is not None else "none")


main()
