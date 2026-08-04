struct Purchase { customer: String, amount: Int }
fn main() {
    let purchases = [Purchase { customer: "Ada", amount: 5 }, Purchase { customer: "Grace", amount: 7 }, Purchase { customer: "Ada", amount: 3 }]
    let mut totals: Map<String, Int> = {}
    for purchase in purchases { totals = totals.add(purchase.customer, purchase.amount) }
    println(totals.get("Ada") or 0)
    println(totals.get("Grace") or 0)
}
