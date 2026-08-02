struct Purchase {
    customer: String,
    amount: Int,
}

fn main() {
    let purchases = [
        Purchase { customer: "Ada", amount: 5 },
        Purchase { customer: "Grace", amount: 7 },
        Purchase { customer: "Ada", amount: 3 },
    ]
    let mut totals: Map<String, Int> = {}
    for purchase in purchases {
        let current = totals.get(purchase.customer) or 0
        totals = totals.set(purchase.customer, current + purchase.amount)
    }
    println(totals.get("Ada") or 0)
    println(totals.get("Grace") or 0)
}
