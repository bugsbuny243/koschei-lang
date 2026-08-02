package main

import "fmt"

func main() {
	values := []int{1, 2, 3, 4, 5, 6, 7}
	for index := 0; index < len(values); index += 3 {
		end := index + 3
		if end > len(values) {
			end = len(values)
		}
		fmt.Println(values[index:end])
	}
}
