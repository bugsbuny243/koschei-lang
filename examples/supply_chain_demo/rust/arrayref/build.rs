// Runs on the developer's machine during `cargo build`, before any of the
// application's code. The August 2026 crates.io attack used this hook to
// download and start a backdoor. This demo only writes a marker file.
use std::{env, fs, path::Path};

fn main() {
    let demo = env::var("SUPPLY_CHAIN_DEMO_DIR").unwrap_or_else(|_| ".".into());
    let marker = Path::new(&demo).join("build_time_payload_ran.txt");
    let _ = fs::write(&marker, "build.rs ran during cargo build\n");
    println!("cargo:rerun-if-changed=build.rs");
}
