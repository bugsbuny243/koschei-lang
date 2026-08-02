package main

import "fmt"

type Purchase struct {
	Customer string
	Amount   int
}

func main() {
	purchases := []Purchase{{"Ada", 5}, {"Grace", 7}, {"Ada", 3}}
	totals := map[string]int{}
	for _, purchase := range purchases {
		totals[purchase.Customer] += purchase.Amount
	}
	fmt.Println(totals["Ada"])
	fmt.Println(totals["Grace"])
}
