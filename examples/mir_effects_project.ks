fn read_config(disk: DiskReadCaps, path: String) -> String or Error {
    return disk.read(path) or return Error("cannot read")
}

fn load_config(disk: DiskReadCaps, path: String) -> String or Error {
    return read_config(disk, path) or return Error("cannot load")
}

fn main() {
    println("effect graph ready")
}
