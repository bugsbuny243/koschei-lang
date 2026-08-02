package main

import (
    "encoding/csv"
    "fmt"
    "strings"
)

func main() {
    reader := csv.NewReader(strings.NewReader("name,active\nAda,true\nLin,false\nGrace,true"))
    rows, err := reader.ReadAll()
    if err != nil {
        panic(err)
    }
    for _, row := range rows[1:] {
        if row[1] == "true" {
            fmt.Println(row[0])
        }
    }
}
