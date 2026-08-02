package main

import (
    "fmt"
    "os"
    "strings"
)

func main() {
    raw, err := os.ReadFile("bench/ceremony/fixtures/lines.txt")
    if err != nil {
        panic(err)
    }
    fmt.Println(len(strings.Split(string(raw), "\n")))
}
