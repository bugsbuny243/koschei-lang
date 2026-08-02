package main

import (
    "encoding/json"
    "fmt"
    "net/http"
)

func main() {
    response, err := http.Get("https://api.example.com/data")
    if err != nil {
        panic(err)
    }
    defer response.Body.Close()
    var value any
    if err := json.NewDecoder(response.Body).Decode(&value); err != nil {
        panic(err)
    }
    canonical, err := json.Marshal(value)
    if err != nil {
        panic(err)
    }
    fmt.Println(string(canonical))
}
