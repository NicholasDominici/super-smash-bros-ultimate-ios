// Refuse accidental build artifacts inside the source checkout.
use std::path::Path;

fn main() {
    let manifest = std::env::var("CARGO_MANIFEST_DIR").expect("Cargo manifest directory");
    let repo = Path::new(&manifest).parent().unwrap().parent().unwrap();
    let output = std::env::var("OUT_DIR").expect("Cargo output directory");
    let output = Path::new(&output)
        .canonicalize()
        .expect("Cargo created OUT_DIR");
    let repo = repo.canonicalize().expect("source checkout exists");
    assert!(
        !output.starts_with(repo),
        "Set CARGO_TARGET_DIR to an absolute directory outside the source checkout"
    );
}
