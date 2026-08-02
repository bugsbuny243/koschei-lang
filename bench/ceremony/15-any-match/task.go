package main

import "fmt"

func main() {
	values := []int{3, 7, 12, 5}
	found := false
	for _, value := range values {
		if value > 10 {
			found = true
			break
		}
	}
	if found {
		fmt.Println("found")
	} else {
		fmt.Println("missing")
	}
}
