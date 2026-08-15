fn save(state: PersistCaps, payload: String) -> String or Error {
    let committed = state.commit(payload) or return Error("state commit failed")
    return payload
}

fn load(state: PersistCaps) -> String or Error {
    return state.load() or return Error("state load failed")
}

fn main() {}
