from collections import Counter


def main() -> None:
    words = "red blue red green blue red yellow".split()
    counts = Counter(words)
    for word, count in counts.most_common(3):
        print(f"{word}:{count}")


main()
