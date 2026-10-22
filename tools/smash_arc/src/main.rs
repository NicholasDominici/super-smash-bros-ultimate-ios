//! Read-only ARC inventory and targeted extraction into a new private directory.
mod effects;
use serde::Serialize;
use sha2::{Digest, Sha256};
use smash_arc::{hash40, ArcFile, ArcLookup, HashLabels, Region};
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{BufReader, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const HELP: &str = "smash-arc-tool <list|extract|shader-archives|effect-shaders> --arc <data.arc> [options]\n\
  --extensions <comma-separated>  Default: nro,nushdb,nufxlb\n\
  --region <region>              Default: us_en\n\
  --labels <hash labels file>     Optional local newline-separated path labels\n\
  --out <new private directory>   Required for extract; must be outside source\n\
  --max-file-bytes <integer>      Default: 268435456 (256 MiB)\n\
  --max-total-bytes <integer>     Default: 4294967296 (4 GiB)\n\
Regions: jp_ja,us_en,us_fr,us_es,eu_en,eu_fr,eu_es,eu_de,eu_nl,eu_it,eu_ru,kr_ko,zh_cn,zh_tw\n\
list emits JSON to stdout; extract writes flat hash-named files and manifest.json.\n\
Only selected extension hashes are decoded; the input archive remains unchanged.\n\
shader-archives keeps BNSH members of .arc SARC resources; effect-shaders keeps EFFN/EFT2 shader carriers.";

#[derive(Debug)]
struct Args {
    extract: bool,
    shader_archives: bool,
    effect_shaders: bool,
    arc: PathBuf,
    extensions: BTreeSet<String>,
    region: Region,
    labels: Option<PathBuf>,
    output: Option<PathBuf>,
    max_file_bytes: u64,
    max_total_bytes: u64,
}

#[derive(Debug, Serialize)]
struct Entry {
    hash40: String,
    extension: String,
    label: Option<String>,
    offset: u64,
    stored_bytes: u64,
    decoded_bytes: u64,
    compressed: bool,
    uses_zstd: bool,
    shared: bool,
    regional: bool,
    localized: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    output: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    sha256: Option<String>,
}

#[derive(Serialize)]
struct Manifest {
    schema: u32,
    operation: &'static str,
    archive_bytes: u64,
    archive_version: u32,
    region: String,
    selected_extensions: Vec<String>,
    selected_count: usize,
    selected_decoded_bytes: u64,
    entries: Vec<Entry>,
    #[serde(skip_serializing_if = "Option::is_none")]
    shader_members: Option<Vec<ShaderMember>>,
}

#[derive(Serialize)]
struct ShaderMember {
    archive_hash40: String,
    member_path: String,
    output: String,
    decoded_bytes: u64,
    sha256: String,
}

/// Parse an explicit region rather than accepting upstream's unknown-to-None fallback.
fn parse_region(value: &str) -> Result<Region, String> {
    let region: Region = value.parse().unwrap(); // Upstream error type is Infallible.
    if region == Region::None {
        Err(format!("unknown region {value:?}; see --help"))
    } else {
        Ok(region)
    }
}

/// Limit suffixes to ASCII components; labels never become output paths.
fn parse_extensions(value: &str) -> Result<BTreeSet<String>, String> {
    let mut out = BTreeSet::new();
    for ext in value.split(',') {
        let ext = ext.strip_prefix('.').unwrap_or(ext).to_ascii_lowercase();
        if ext.is_empty()
            || ext.len() > 32
            || !ext.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
        {
            return Err("extensions must be nonempty ASCII names separated by commas".into());
        }
        out.insert(ext);
    }
    Ok(out)
}

fn positive_limit(value: &str) -> Result<u64, String> {
    value
        .parse::<u64>()
        .ok()
        .filter(|n| *n > 0)
        .ok_or_else(|| format!("invalid positive byte limit {value:?}"))
}

fn parse_args(values: &[String]) -> Result<Args, String> {
    let extract = match values.first().map(String::as_str) {
        Some("list") => false,
        Some("extract" | "shader-archives" | "effect-shaders") => true,
        _ => return Err(
            "first argument must be list, extract, shader-archives or effect-shaders; see --help"
                .into(),
        ),
    };
    let shader_archives = values[0] == "shader-archives";
    let effect_shaders = values[0] == "effect-shaders";
    let mut options = BTreeMap::new();
    let mut i = 1;
    while i < values.len() {
        let flag = &values[i];
        if !matches!(
            flag.as_str(),
            "--arc"
                | "--extensions"
                | "--region"
                | "--labels"
                | "--out"
                | "--max-file-bytes"
                | "--max-total-bytes"
        ) {
            return Err(format!("unknown option {flag:?}"));
        }
        let value = values
            .get(i + 1)
            .ok_or_else(|| format!("{flag} needs a value"))?;
        if value.starts_with("--") || value.is_empty() {
            return Err(format!("{flag} needs a value"));
        }
        if options.insert(flag.as_str(), value.as_str()).is_some() {
            return Err(format!("duplicate option {flag}"));
        }
        i += 2;
    }
    let arc = options.get("--arc").ok_or("--arc is required")?;
    let output = options.get("--out").map(PathBuf::from);
    if extract && output.is_none() {
        return Err("extract requires --out".into());
    }
    if !extract && output.is_some() {
        return Err("list emits JSON to stdout; --out is only for extract".into());
    }
    Ok(Args {
        extract,
        shader_archives,
        effect_shaders,
        arc: PathBuf::from(arc),
        output,
        labels: options.get("--labels").map(PathBuf::from),
        region: parse_region(options.get("--region").copied().unwrap_or("us_en"))?,
        extensions: parse_extensions(options.get("--extensions").copied().unwrap_or(
            if shader_archives {
                "arc"
            } else if effect_shaders {
                "eff"
            } else {
                "nro,nushdb,nufxlb"
            },
        ))?,
        max_file_bytes: positive_limit(
            options
                .get("--max-file-bytes")
                .copied()
                .unwrap_or("268435456"),
        )?,
        max_total_bytes: positive_limit(
            options
                .get("--max-total-bytes")
                .copied()
                .unwrap_or("4294967296"),
        )?,
    })
}

/// Resolve an existing parent first so a symlink cannot bypass the source boundary.
fn new_private_directory(path: &Path, source: &Path) -> Result<PathBuf, String> {
    let name = path.file_name().ok_or("output must name a new directory")?;
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let parent = parent
        .canonicalize()
        .map_err(|e| format!("output parent must already exist: {e}"))?;
    let resolved = parent.join(name);
    let source = source.canonicalize().map_err(|e| e.to_string())?;
    if resolved.starts_with(source) {
        return Err("game output must be outside the source checkout".into());
    }
    if fs::symlink_metadata(&resolved).is_ok() {
        return Err("output already exists; choose a new private directory".into());
    }
    Ok(resolved)
}

/// Reject overflow, truncated stored ranges and oversized output before decoding.
fn check_entry(entry: &Entry, archive_len: u64, max_file: u64) -> Result<(), String> {
    if entry.decoded_bytes > max_file {
        return Err(format!(
            "{} would decode to {} bytes, exceeding --max-file-bytes",
            entry.hash40, entry.decoded_bytes
        ));
    }
    let end = entry
        .offset
        .checked_add(entry.stored_bytes)
        .ok_or("stored range overflow")?;
    if end > archive_len {
        return Err(format!(
            "{} stored range is past the archive end",
            entry.hash40
        ));
    }
    if entry.compressed && !entry.uses_zstd {
        return Err(format!("{} uses unsupported ARC compression", entry.hash40));
    }
    if !entry.compressed && entry.stored_bytes != entry.decoded_bytes {
        return Err(format!("{} uncompressed lengths differ", entry.hash40));
    }
    Ok(())
}

fn write_new_file(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    file.write_all(bytes).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())
}

/// Stop at one byte beyond the declared size, including malformed zstd output.
fn bounded_decode(reader: impl Read, expected: u64) -> Result<Vec<u8>, String> {
    let limit = expected.checked_add(1).ok_or("decoded size overflow")?;
    let mut bytes = Vec::new();
    reader
        .take(limit)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() as u64 != expected {
        return Err(format!(
            "decoded length {} differs from expected {expected}",
            bytes.len()
        ));
    }
    Ok(bytes)
}

/// Use upstream's resolved offsets, with a bounded streaming decoder for payloads.
fn extract_entry(arc: &ArcFile, entry: &Entry) -> Result<Vec<u8>, String> {
    let mut reader = arc.get_file_reader();
    reader
        .seek(SeekFrom::Start(entry.offset))
        .map_err(|e| e.to_string())?;
    let reader = reader.take(entry.stored_bytes);
    if entry.compressed {
        if !entry.uses_zstd {
            return Err("unsupported ARC compression; only zstd is supported".into());
        }
        let decoder = zstd::stream::read::Decoder::new(reader).map_err(|e| e.to_string())?;
        bounded_decode(decoder, entry.decoded_bytes)
    } else {
        bounded_decode(reader, entry.decoded_bytes)
    }
}

/// Checked SARC directory traversal; only shader-bearing members are retained.
/// Names are bounded by the SFNT area, never split across the archive payload.
fn sarc_shaders(data: &[u8]) -> Result<Vec<(String, &[u8])>, String> {
    if data.get(..4) != Some(b"SARC") {
        return Err("nested .arc resource is not a SARC archive".into());
    }
    let little = match data.get(6..8) {
        Some([0xff, 0xfe]) => true,
        Some([0xfe, 0xff]) => false,
        _ => return Err("invalid SARC byte order".into()),
    };
    let u16_at = |p: usize| -> Result<usize, String> {
        let b: [u8; 2] = data
            .get(p..p + 2)
            .ok_or("truncated SARC field")?
            .try_into()
            .unwrap();
        Ok(if little {
            u16::from_le_bytes(b)
        } else {
            u16::from_be_bytes(b)
        } as usize)
    };
    let u32_at = |p: usize| -> Result<usize, String> {
        let b: [u8; 4] = data
            .get(p..p + 4)
            .ok_or("truncated SARC field")?
            .try_into()
            .unwrap();
        Ok(if little {
            u32::from_le_bytes(b)
        } else {
            u32::from_be_bytes(b)
        } as usize)
    };
    let header = u16_at(4)?;
    let size = u32_at(8)?;
    let payload = u32_at(12)?;
    if header < 20
        || size > data.len()
        || payload > size
        || data.get(header..header + 4) != Some(b"SFAT")
    {
        return Err("invalid SARC/SFAT bounds".into());
    }
    let fat_header = u16_at(header + 4)?;
    let count = u16_at(header + 6)?;
    let nodes = header + fat_header;
    let sfnt = nodes + 16 * count;
    if fat_header != 12
        || data.get(sfnt..sfnt + 4) != Some(b"SFNT")
        || u16_at(sfnt + 4)? != 8
        || sfnt + 8 > payload
    {
        return Err("invalid SARC node/name table bounds".into());
    }
    let names = sfnt + 8;
    let mut result = Vec::new();
    for i in 0..count {
        let row = nodes + 16 * i;
        let attr = u32_at(row + 4)?;
        let start = u32_at(row + 8)?;
        let end = u32_at(row + 12)?;
        if start > end || end > size - payload {
            return Err("SARC member range escapes the payload".into());
        }
        let name = if attr >> 24 == 0 {
            format!("#{i}")
        } else {
            let offset = names + (attr & 0xffffff) * 4;
            let tail = data
                .get(offset..payload)
                .ok_or("SARC member name offset escapes SFNT")?;
            let end = tail
                .iter()
                .take(4097)
                .position(|b| *b == 0)
                .ok_or("unterminated/oversized SARC member name")?;
            let name =
                std::str::from_utf8(&tail[..end]).map_err(|_| "non-UTF8 SARC member name")?;
            if name.is_empty()
                || name.starts_with('/')
                || name.contains('\\')
                || name.chars().any(char::is_control)
                || name
                    .split('/')
                    .any(|p| p.is_empty() || p == "." || p == "..")
            {
                return Err("unsafe SARC member name".into());
            }
            name.to_owned()
        };
        let bytes = &data[payload + start..payload + end];
        if bytes.windows(8).any(|w| w == b"BNSH\0\0\0\0") {
            result.push((name, bytes));
        }
    }
    Ok(result)
}

fn run(args: Args) -> Result<(), String> {
    let input = File::open(&args.arc).map_err(|e| format!("opening ARC: {e}"))?;
    let meta = input.metadata().map_err(|e| e.to_string())?;
    if !meta.is_file() {
        return Err("--arc must be a regular file".into());
    }
    let archive_len = meta.len();
    let source = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .unwrap()
        .parent()
        .unwrap();
    let output = args
        .output
        .as_ref()
        .map(|p| new_private_directory(p, source))
        .transpose()?;
    let labels = args
        .labels
        .as_ref()
        .map(HashLabels::from_file)
        .transpose()
        .map_err(|e| format!("reading labels: {e}"))?;
    // ArcFile reads/decompresses the index, then seeks only to selected resource ranges.
    let arc =
        ArcFile::from_reader(BufReader::new(input)).map_err(|e| format!("parsing ARC: {e}"))?;
    let ext_hashes: BTreeMap<u64, &str> = args
        .extensions
        .iter()
        .map(|s| (hash40(s).as_u64(), s.as_str()))
        .collect();
    let mut selection = BTreeMap::new();
    let mut total = 0u64;
    for path in arc.get_file_paths() {
        let Some(ext) = ext_hashes.get(&path.ext.hash40().as_u64()) else {
            continue;
        };
        let hash = path.path.hash40();
        if selection.contains_key(&hash.as_u64()) {
            continue;
        }
        let metadata = arc
            .get_file_metadata(hash, args.region)
            .map_err(|e| format!("metadata for {:#x}: {e}", hash.as_u64()))?;
        let entry = Entry {
            hash40: format!("{:010x}", hash.as_u64()),
            extension: (*ext).into(),
            label: labels
                .as_ref()
                .and_then(|l| hash.label(l))
                .map(str::to_owned),
            offset: metadata.offset,
            stored_bytes: metadata.comp_size,
            decoded_bytes: metadata.decomp_size,
            compressed: metadata.is_compressed,
            uses_zstd: metadata.uses_zstd,
            shared: metadata.is_shared,
            regional: metadata.is_regional,
            localized: metadata.is_localized,
            output: None,
            sha256: None,
        };
        check_entry(&entry, archive_len, args.max_file_bytes)?;
        total = total
            .checked_add(entry.decoded_bytes)
            .ok_or("selected byte count overflow")?;
        if total > args.max_total_bytes {
            return Err(format!(
                "selected resources exceed --max-total-bytes ({})",
                args.max_total_bytes
            ));
        }
        selection.insert(hash.as_u64(), entry);
    }
    if selection.is_empty() {
        return Err("no matching extensions found; no output written".into());
    }
    let mut members = Vec::new();
    let mut written = BTreeSet::new();
    if let Some(directory) = &output {
        fs::create_dir(directory).map_err(|e| format!("creating new private output: {e}"))?;
        let count = selection.len();
        for (i, entry) in selection.values_mut().enumerate() {
            let bytes = extract_entry(&arc, entry)
                .map_err(|e| format!("extracting {}: {e}", entry.hash40))?;
            entry.sha256 = Some(format!("{:x}", Sha256::digest(&bytes)));
            if args.shader_archives || args.effect_shaders {
                let payloads = if args.effect_shaders {
                    effects::shaders(&bytes).map_err(|e| format!("EFFN {}: {e}", entry.hash40))?
                } else {
                    sarc_shaders(&bytes).map_err(|e| format!("SARC {}: {e}", entry.hash40))?
                };
                for (name, data) in payloads {
                    let digest = format!("{:x}", Sha256::digest(data));
                    let filename = format!("{digest}.bnsh");
                    if written.insert(filename.clone()) {
                        write_new_file(&directory.join(&filename), data)?;
                    }
                    members.push(ShaderMember {
                        archive_hash40: entry.hash40.clone(),
                        member_path: name,
                        output: filename,
                        decoded_bytes: data.len() as u64,
                        sha256: digest,
                    });
                }
            } else {
                let filename = format!("{}.{}", entry.hash40, entry.extension);
                write_new_file(&directory.join(&filename), &bytes)?;
                entry.output = Some(filename);
            }
            if i == 0 || (i + 1) % 25 == 0 || i + 1 == count {
                eprintln!("processed {}/{} selected files", i + 1, count);
            }
        }
    }
    let manifest = Manifest {
        schema: 1,
        operation: if args.shader_archives {
            "shader-archives"
        } else if args.effect_shaders {
            "effect-shaders"
        } else if args.extract {
            "extract"
        } else {
            "list"
        },
        archive_bytes: archive_len,
        archive_version: arc.file_system.fs_header.version,
        region: args.region.to_string(),
        selected_extensions: args.extensions.into_iter().collect(),
        selected_count: selection.len(),
        selected_decoded_bytes: total,
        entries: selection.into_values().collect(),
        shader_members: if args.shader_archives || args.effect_shaders {
            Some(members)
        } else {
            None
        },
    };
    let mut encoded = serde_json::to_vec_pretty(&manifest).map_err(|e| e.to_string())?;
    encoded.push(b'\n');
    if let Some(output) = output {
        write_new_file(&output.join("manifest.json"), &encoded)?;
        eprintln!(
            "complete: {} files, {} decoded bytes",
            manifest.selected_count, total
        );
    } else {
        std::io::stdout()
            .lock()
            .write_all(&encoded)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn main() {
    let values: Vec<String> = std::env::args().skip(1).collect();
    if values.iter().any(|s| s == "--help" || s == "-h") {
        println!("{HELP}");
        return;
    }
    if let Err(error) = parse_args(&values).and_then(run) {
        eprintln!("error: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sarc_fixture(little: bool) -> Vec<u8> {
        let mut data = vec![0; 136];
        data[..4].copy_from_slice(b"SARC");
        let put16 = |d: &mut [u8], p, n: u16| {
            d[p..p + 2].copy_from_slice(&if little {
                n.to_le_bytes()
            } else {
                n.to_be_bytes()
            })
        };
        let put32 = |d: &mut [u8], p, n: u32| {
            d[p..p + 4].copy_from_slice(&if little {
                n.to_le_bytes()
            } else {
                n.to_be_bytes()
            })
        };
        put16(&mut data, 4, 20);
        put16(&mut data, 6, 0xfeff);
        put32(&mut data, 8, 136);
        put32(&mut data, 12, 128);
        data[20..24].copy_from_slice(b"SFAT");
        put16(&mut data, 24, 12);
        put16(&mut data, 26, 1);
        put32(&mut data, 36, 0x01000000);
        put32(&mut data, 44, 8);
        data[48..52].copy_from_slice(b"SFNT");
        put16(&mut data, 52, 8);
        data[56..75].copy_from_slice(b"bgsh/archive.bnsh\0\0");
        data[128..136].copy_from_slice(b"BNSH\0\0\0\0");
        data
    }

    #[test]
    fn nested_mode_selects_arcs_and_retains_exact_members_in_both_byte_orders() {
        let a = args(&["shader-archives", "--arc", "data.arc", "--out", "private"]).unwrap();
        assert!(a.shader_archives);
        assert_eq!(a.extensions, BTreeSet::from(["arc".to_owned()]));
        for little in [true, false] {
            let fixture = sarc_fixture(little);
            let members = sarc_shaders(&fixture).unwrap();
            assert_eq!(
                members,
                vec![("bgsh/archive.bnsh".to_owned(), &b"BNSH\0\0\0\0"[..])]
            );
        }
    }

    #[test]
    fn effect_mode_selects_only_effect_resources() {
        let a = args(&["effect-shaders", "--arc", "data.arc", "--out", "private"]).unwrap();
        assert!(a.effect_shaders && a.extract && !a.shader_archives);
        assert_eq!(a.extensions, BTreeSet::from(["eff".to_owned()]));
    }

    #[test]
    fn nested_sarc_bounds_names_and_member_ranges_before_slicing() {
        for (offset, bytes) in [
            (36, [255, 255, 255, 1]),
            (44, [255, 255, 255, 255]),
            (12, [0, 0, 0, 0]),
        ] {
            let mut data = sarc_fixture(true);
            data[offset..offset + 4].copy_from_slice(&bytes);
            assert!(sarc_shaders(&data).is_err());
        }
        let mut data = sarc_fixture(true);
        data[56..128].fill(b'a');
        assert!(sarc_shaders(&data).is_err());
        let mut data = sarc_fixture(true);
        data[56..59].copy_from_slice(b"../");
        assert!(sarc_shaders(&data).is_err());
        let mut data = sarc_fixture(true);
        data[128] = b'X';
        assert!(sarc_shaders(&data).unwrap().is_empty());
    }

    fn args(values: &[&str]) -> Result<Args, String> {
        parse_args(&values.iter().map(|s| (*s).to_owned()).collect::<Vec<_>>())
    }

    #[test]
    fn cli_requires_explicit_arc_and_extract_destination() {
        assert!(args(&["list"]).is_err());
        assert!(args(&["extract", "--arc", "data.arc"]).is_err());
        assert!(args(&["list", "--arc", "data.arc", "--out", "x"]).is_err());
        assert!(args(&["list", "--arc", "a", "--arc", "b"]).is_err());
        assert!(args(&["list", "--arc", "--region", "us_en"]).is_err());
        assert!(args(&["list", "--arc", "a", "--typo", "x"]).is_err());
    }

    #[test]
    fn extensions_and_regions_do_not_silently_fallback() {
        let parsed = args(&[
            "list",
            "--arc",
            "data.arc",
            "--extensions",
            ".NRO,nushdb,nro",
            "--region",
            "eu_fr",
        ])
        .unwrap();
        assert_eq!(parsed.extensions.len(), 2);
        assert_eq!(parsed.region, Region::EuFrench);
        for bad in ["", "nro,", "../nro", "a/b", "a\\b", "a.b", "こんにちは"] {
            assert!(parse_extensions(bad).is_err(), "{bad}");
        }
        for bad in ["unknown", "none", "", "en"] {
            assert!(parse_region(bad).is_err(), "{bad}");
        }
    }

    #[test]
    fn limits_reject_zero_negative_and_overflow() {
        for bad in ["0", "-1", "18446744073709551616", "1.5", ""] {
            assert!(positive_limit(bad).is_err(), "{bad}");
        }
        assert_eq!(positive_limit("1024").unwrap(), 1024);
    }

    #[test]
    fn selection_rejects_oversize_truncation_and_offset_overflow() {
        let mut entry = Entry {
            hash40: "0123456789".into(),
            extension: "nro".into(),
            label: None,
            offset: 100,
            stored_bytes: 20,
            decoded_bytes: 40,
            compressed: true,
            uses_zstd: true,
            shared: false,
            regional: false,
            localized: false,
            output: None,
            sha256: None,
        };
        assert!(check_entry(&entry, 120, 40).is_ok());
        assert!(check_entry(&entry, 119, 40).is_err());
        assert!(check_entry(&entry, 120, 39).is_err());
        entry.offset = u64::MAX;
        assert!(check_entry(&entry, u64::MAX, 40).is_err());
    }

    #[test]
    fn output_refuses_source_paths_existing_paths_and_symlink_bypasses() {
        let root = std::env::temp_dir().join(format!("smash-arc-path-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        let source = root.join("source");
        fs::create_dir(&source).unwrap();
        assert!(new_private_directory(&source.join("new"), &source).is_err());
        assert!(new_private_directory(&source, &source).is_err());
        assert!(new_private_directory(&root.join("private"), &source).is_ok());
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(&source, root.join("link")).unwrap();
            assert!(new_private_directory(&root.join("link/new"), &source).is_err());
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn write_never_overwrites_existing_file_or_symlink() {
        let root =
            std::env::temp_dir().join(format!("smash-arc-write-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir(&root).unwrap();
        let path = root.join("file");
        write_new_file(&path, b"preserve").unwrap();
        assert!(write_new_file(&path, b"replace").is_err());
        assert_eq!(fs::read(&path).unwrap(), b"preserve");
        #[cfg(unix)]
        {
            let link = root.join("link");
            std::os::unix::fs::symlink(&path, &link).unwrap();
            assert!(write_new_file(&link, b"replace").is_err());
        }
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn decoded_length_is_bounded_even_for_an_unbounded_reader() {
        assert!(bounded_decode(std::io::repeat(0), 16).is_err());
        assert!(bounded_decode(std::io::Cursor::new([0; 15]), 16).is_err());
        assert_eq!(
            bounded_decode(std::io::Cursor::new([1; 16]), 16).unwrap(),
            vec![1; 16]
        );
    }
}
