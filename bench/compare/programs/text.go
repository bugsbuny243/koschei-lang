package main

import (
	"fmt"
	"strings"
)

func main() {
	parts := []string{}
	for i := 0; i < 3000; i++ {
		next := make([]string, len(parts), len(parts)+1)
		copy(next, parts)
		parts = append(next, fmt.Sprintf("item%d", i))
	}
	joined := strings.Join(parts, ",")
	back := strings.Split(joined, ",")
	fmt.Println(len(joined), len(back))
}
