package main

import "fmt"

func main() {
	values := []int{-3, 2, 0, 5, -1}
	negative := []int{}
	nonNegative := []int{}
	for _, value := range values {
		if value < 0 {
			negative = append(negative, value)
		} else {
			nonNegative = append(nonNegative, value)
		}
	}
	fmt.Println(negative)
	fmt.Println(nonNegative)
}
