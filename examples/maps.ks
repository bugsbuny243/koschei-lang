fn main() {
    let customer = { "name": "Ali", "age": 42 }
    let updated = customer.set("city", "Istanbul")
    let name = updated.get("name") or "bilinmiyor"

    println(name)
    println(updated.contains("city"))
    println(updated.keys())
    println(customer)
    println(updated)
}
