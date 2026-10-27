fn main() {
    let limit = std::hint::black_box(300000i64);
    let (mut total, mut i) = (0i64, 0i64);
    while i < limit { total = total.checked_add(i.checked_mul(i).unwrap() % 7).unwrap(); i += 1; }
    println!("{}", total);
}
