package main

import "fmt"

func main() {
    for _, n := range []int{1, 2, 3, 4, 5, 6, 15} {
        if n%15 == 0 {
            fmt.Println("FizzBuzz")
        } else if n%3 == 0 {
            fmt.Println("Fizz")
        } else if n%5 == 0 {
            fmt.Println("Buzz")
        } else {
            fmt.Println(n)
        }
    }
}
