def main() -> None:
    for n in [1, 2, 3, 4, 5, 6, 15]:
        if n % 15 == 0:
            print("FizzBuzz")
        elif n % 3 == 0:
            print("Fizz")
        elif n % 5 == 0:
            print("Buzz")
        else:
            print(n)


main()
