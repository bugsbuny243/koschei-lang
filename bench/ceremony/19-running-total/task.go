package main

import "fmt"

func main() {
	values := []int{5, 3, 2, 7}
	total := 0
	running := make([]int, 0, len(values))
	for _, value := range values {
		total += value
		running = append(running, total)
	}
	fmt.Println(running)
}
