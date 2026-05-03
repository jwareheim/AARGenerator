use std::io::Write;
use std::process::Command;

fn binary() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_BIN_EXE_stellaris-parser"))
}

fn fixture(name: &str) -> std::path::PathBuf {
    let manifest = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
    manifest.parent().unwrap().join("tests").join("fixtures").join(name)
}

fn temp_sav(tag: &str) -> std::path::PathBuf {
    std::env::temp_dir().join(format!("chronicle_test_{tag}.sav"))
}

fn make_zip(entries: &[(&str, &[u8])]) -> Vec<u8> {
    let mut buf = Vec::new();
    let cursor = std::io::Cursor::new(&mut buf);
    let mut zip = zip::ZipWriter::new(cursor);
    let opts = zip::write::SimpleFileOptions::default();
    for (name, data) in entries {
        zip.start_file(*name, opts).unwrap();
        zip.write_all(data).unwrap();
    }
    zip.finish().unwrap();
    buf
}

// ── Schema validation against the anonymised fixture ─────────────────────────

#[test]
fn fixture_parses_and_schema_is_correct() {
    let out = Command::new(binary())
        .args(["extract", fixture("sample.sav").to_str().unwrap()])
        .output()
        .expect("failed to run binary");

    assert_eq!(
        out.status.code(),
        Some(0),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );

    let json: serde_json::Value =
        serde_json::from_slice(&out.stdout).expect("stdout is not valid JSON");

    // Top-level meta
    assert_eq!(json["patch_version"], "Cetus v4.3.2");
    assert_eq!(json["date"], "2294.04.25");
    assert_eq!(json["ironman"], true);
    assert_eq!(json["player_country_id"], 0);

    // Empire
    assert_eq!(json["empire"]["authority"], "auth_imperial");
    let ethics = json["empire"]["ethics"].as_array().unwrap();
    assert!(
        ethics.iter().any(|e| e == "ethic_militarist"),
        "missing ethic_militarist"
    );
    assert!(
        ethics.iter().any(|e| e == "ethic_fanatic_spiritualist"),
        "missing ethic_fanatic_spiritualist"
    );
    assert_eq!(json["empire"]["civics"].as_array().unwrap().len(), 2);

    // State
    assert_eq!(json["state"]["owned_planet_count"], 7);
    assert!(json["state"]["fleet_power"].as_u64().unwrap() > 0);
    assert!(json["state"]["monthly_energy"].as_f64().unwrap() > 0.0);
    assert!(!json["state"]["traditions"].as_array().unwrap().is_empty());
    assert_eq!(json["state"]["ascension_perks"].as_array().unwrap().len(), 3);
    assert_eq!(
        json["state"]["recent_technologies"].as_array().unwrap().len(),
        10
    );

    // Leaders and wars
    assert!(!json["leaders"].as_array().unwrap().is_empty());
    assert_eq!(json["wars"].as_array().unwrap().len(), 1);
    assert_eq!(json["wars"][0]["start_date"], "2294.04.18");

    // Diplomacy block exists
    assert!(json["diplomacy"].is_object());
}

// ── Binary-encoded save exits 5 ───────────────────────────────────────────────

#[test]
fn binary_encoded_save_exits_5() {
    let path = temp_sav("binary_format");
    let data = make_zip(&[
        ("meta", b"date=\"2200.01.01\"\nplayer_portrait=\"mam1\"\nironan=no"),
        // null byte in the first 256 bytes triggers the binary-format check
        (
            "gamestate",
            b"\x00\x01\x02\x03 this is binary-encoded content",
        ),
    ]);
    std::fs::write(&path, &data).unwrap();

    let out = Command::new(binary())
        .args(["extract", path.to_str().unwrap()])
        .output()
        .expect("failed to run binary");

    let _ = std::fs::remove_file(&path);

    assert_eq!(
        out.status.code(),
        Some(5),
        "expected exit 5, got {:?} — stderr: {}",
        out.status.code(),
        String::from_utf8_lossy(&out.stderr)
    );
}

// ── Corrupted / truncated input exits 2 or 3 ─────────────────────────────────

#[test]
fn corrupted_input_exits_cleanly() {
    let path = temp_sav("corrupted");
    // Starts with PK (looks like ZIP) but is then garbage — ZipArchive::new should fail
    std::fs::write(&path, b"PK\x03\x04 truncated garbage \xff\xfe\x00\x01").unwrap();

    let out = Command::new(binary())
        .args(["extract", path.to_str().unwrap()])
        .output()
        .expect("failed to run binary");

    let _ = std::fs::remove_file(&path);

    let code = out.status.code().unwrap_or(-1);
    assert!(
        code == 2 || code == 3,
        "expected exit 2 or 3, got {} — stderr: {}",
        code,
        String::from_utf8_lossy(&out.stderr)
    );
}
