fn main() {
    let defaults: Map<String, Int> = {"port": 8080, "workers": 2}
    let supplied: Map<String, Int> = {"workers": 4}
    let config = defaults.merge(supplied)
    println(config.get("port") or 8080)
    println(config.get("workers") or 2)
}
