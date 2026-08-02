package main

import "fmt"

func main() {
	groups := [][]int{{1, 2}, {3}, {4, 5}}
	flat := []int{}
	for _, group := range groups {
		flat = append(flat, group...)
	}
	fmt.Println(flat)
}
