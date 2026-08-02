package main

import "fmt"

func main() {
    found := 0
    ok := false
    for _, value := range []int{1, 3, 6, 8} {
        if value%2 != 0 {
            continue
        }
        found = value
        ok = true
        break
    }
    if ok {
        fmt.Println(found)
    } else {
        fmt.Println("none")
    }
}
