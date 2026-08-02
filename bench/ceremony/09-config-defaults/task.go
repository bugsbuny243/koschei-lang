package main

import "fmt"

func main() {
    config := map[string]int{"port": 8080, "workers": 2}
    supplied := map[string]int{"workers": 4}
    for key, value := range supplied {
        config[key] = value
    }
    fmt.Println(config["port"])
    fmt.Println(config["workers"])
}
