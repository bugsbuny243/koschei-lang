fn positive(value: Int) -> Bool {
    return value > 0
}

fn main() {
    let names = "  ali,ayşe,mehmet  ".trim().split(",")
    let scores = [3, -1, 2]
    let positive_scores = scores.filter(positive) or []
    let ordered = positive_scores.sort() or []

    println("Kişiler: {" | ".join(names) or "?"}")
    println("Pozitif skorlar: {ordered}")
    println("Kişi sayısı: {names.length()}")
}
