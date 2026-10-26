package main

import "fmt"

func main() {
	var total, i int64
	for i < 300000 {
		total = total + i*i%7
		i++
	}
	fmt.Println(total)
}
