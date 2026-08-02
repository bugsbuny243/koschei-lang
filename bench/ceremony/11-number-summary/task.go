package main

import "fmt"

func main() {
	values := []int{4, 8, 15, 16, 23, 42}
	total, minimum, maximum := 0, values[0], values[0]
	for _, value := range values {
		total += value
		if value < minimum {
			minimum = value
		}
		if value > maximum {
			maximum = value
		}
	}
	fmt.Printf("sum=%d min=%d max=%d\n", total, minimum, maximum)
}
