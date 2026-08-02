package main

import (
    "encoding/json"
    "fmt"
)

func main() {
    var value map[string]any
    if err := json.Unmarshal([]byte(`{"b":2,"a":1.00}`), &value); err != nil {
        panic(err)
    }
    canonical, err := json.Marshal(value)
    if err != nil {
        panic(err)
    }
    fmt.Println(string(canonical))
}
