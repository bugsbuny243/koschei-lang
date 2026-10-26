fn main() {
    let mut parts: Vec<String> = Vec::new();
    for i in 0..std::hint::black_box(3000) {
        let mut next = parts.clone();
        next.push(format!("item{}", i));
        parts = next;
    }
    let joined = parts.join(",");
    let back: Vec<&str> = joined.split(',').collect();
    println!("{} {}", joined.len(), back.len());
}
