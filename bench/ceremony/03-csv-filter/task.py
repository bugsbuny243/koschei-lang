import csv
import io


def main() -> None:
    text = "name,active\nAda,true\nLin,false\nGrace,true"
    for row in csv.DictReader(io.StringIO(text)):
        if row["active"] == "true":
            print(row["name"])


main()
