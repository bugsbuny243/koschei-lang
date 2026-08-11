struct Pending {}
struct Settled {}

stateful struct Settlement<S> starts Pending {
    id: Int,
    state: S,
}

pure transition fn settle(item: Settlement<Pending>) -> Settlement<Settled> {
    return Settlement { id: item.id, state: Settled {} }
}

pure fn settled_id(item: Settlement<Settled>) -> Int {
    return item.id
}

fn main() {
    let pending = Settlement { id: 42, state: Pending {} }
    let settled = settle(pending)
    println(settled_id(settled))
}
