from pathlib import Path


def main() -> None:
    text = Path("bench/ceremony/fixtures/lines.txt").read_text()
    print(len(text.split("\n")))


main()
