package main

import "fmt"

func main() {
	values := []int{1, 2, 3, 4}
	squares := make([]int, 0, len(values))
	for _, value := range values {
		squares = append(squares, value*value)
	}
	fmt.Println(squares)
}
