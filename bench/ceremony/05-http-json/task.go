package main

import (
    "fmt"
    "io"
    "net/http"
)

func main() {
    response, err := http.Get("https://api.example.com/data")
    if err != nil {
        panic(err)
    }
    defer response.Body.Close()
    body, err := io.ReadAll(response.Body)
    if err != nil {
        panic(err)
    }
    fmt.Println(string(body))
}
