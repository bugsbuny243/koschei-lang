package main

import "fmt"

func main() {
    success := false
    for attempt := 1; attempt <= 3; attempt++ {
        if attempt == 2 {
            success = true
            break
        }
        fmt.Printf("retry %d\n", attempt)
    }
    fmt.Printf("success: %t\n", success)
}
