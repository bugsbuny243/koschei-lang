package main

import (
    "fmt"
    "sort"
    "strings"
)

type row struct {
    word  string
    count int
}

func main() {
    counts := map[string]int{}
    for _, word := range strings.Fields("red blue red green blue red yellow") {
        counts[word]++
    }
    rows := make([]row, 0, len(counts))
    for word, count := range counts {
        rows = append(rows, row{word, count})
    }
    sort.Slice(rows, func(i, j int) bool { return rows[i].count > rows[j].count })
    for _, item := range rows[:3] {
        fmt.Printf("%s:%d\n", item.word, item.count)
    }
}
