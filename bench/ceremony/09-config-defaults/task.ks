fn main() {
    let defaults: Map<String, Int> = {"port": 8080, "workers": 2}
    let supplied: Map<String, Int> = {"workers": 4}
    let mut config = defaults
    for key in supplied.keys() {
        config = config.set(key, supplied.get(key) or 0)
    }
    println(config.get("port") or 8080)
    println(config.get("workers") or 2)
}
