package main

import "fmt"

func main() {
    left := []string{"alpha", "beta", "gamma"}
    right := []string{"alpha", "BETA", "gamma"}
    limit := len(left)
    if len(right) < limit {
        limit = len(right)
    }
    for index := 0; index < limit; index++ {
        if left[index] != right[index] {
            fmt.Printf("difference at %d\n", index)
            break
        }
    }
}
