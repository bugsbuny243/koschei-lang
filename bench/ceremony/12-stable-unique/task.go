package main

import (
	"fmt"
	"strings"
)

func main() {
	values := []string{"a", "b", "a", "c", "b"}
	seen := map[string]bool{}
	unique := []string{}
	for _, value := range values {
		if seen[value] {
			continue
		}
		seen[value] = true
		unique = append(unique, value)
	}
	fmt.Println(strings.Join(unique, ","))
}
