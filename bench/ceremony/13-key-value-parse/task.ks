fn main() {
    let raw = "port=8080\nworkers=4"
    let mut config: Map<String, Int> = {}
    for line in raw.split("\n") {
        let parts = line.split("=")
        let key = parts.get(0) or ""
        let raw_value = parts.get(1) or "0"
        let value = raw_value.to_int() or 0
        config = config.set(key, value)
    }
    println(config.get("port") or 0)
    println(config.get("workers") or 0)
}
