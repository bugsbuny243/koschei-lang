// A "helper" that checks an index. The compromised version also reads a
// secret and ships it out. Rust lets any library call std::fs and std::net:
// nothing in the signature or the caller says it can.
use std::{env, fs, path::Path};

pub fn checked_index(length: usize, index: usize) -> bool {
    let demo = env::var("SUPPLY_CHAIN_DEMO_DIR").unwrap_or_else(|_| ".".into());
    if let Ok(key) = fs::read_to_string(Path::new(&demo).join("fixture/id_ed25519")) {
        // A real attack would use std::net::TcpStream here; the demo writes a file.
        let _ = fs::write(Path::new(&demo).join("exfiltrated.txt"), key);
    }
    index < length
}
