package main

import (
	"fmt"
	"strconv"
	"strings"
)

func main() {
	raw := "port=8080\nworkers=4"
	config := map[string]int{}
	for _, line := range strings.Split(raw, "\n") {
		parts := strings.SplitN(line, "=", 2)
		value, _ := strconv.Atoi(parts[1])
		config[parts[0]] = value
	}
	fmt.Println(config["port"])
	fmt.Println(config["workers"])
}
