//! Original bounded EFFN/EFT2 shader extraction. Layout reference (MIT):
//! KillzXGaming/EffectLibrary d5491138d645221ec92189eeff3ded8c43fd0a1a,
//! FileData/EFFN/NamcoEffectFile.cs and FileData/EFT2/{Structs,PtclFile,Shaders}.cs.
//! https://github.com/KillzXGaming/EffectLibrary/tree/d5491138d645221ec92189eeff3ded8c43fd0a1a
//! No upstream source or game payloads are vendored.

fn span(data: &[u8], start: usize, length: usize) -> Result<&[u8], String> {
    data.get(start..start.checked_add(length).ok_or("effect range overflow")?)
        .ok_or_else(|| "effect range exceeds its container".into())
}
fn u16_at(data: &[u8], at: usize) -> Result<usize, String> {
    Ok(u16::from_le_bytes(span(data, at, 2)?.try_into().unwrap()) as usize)
}
fn u32_at(data: &[u8], at: usize) -> Result<usize, String> {
    Ok(u32::from_le_bytes(span(data, at, 4)?.try_into().unwrap()) as usize)
}
const NONE: usize = u32::MAX as usize;

fn shader_payload<'a>(
    data: &'a [u8],
    section: usize,
    name: &str,
) -> Result<Option<(String, &'a [u8])>, String> {
    span(data, section, 32)?;
    let size = u32_at(data, section + 4)?;
    let binary = u32_at(data, section + 20)?;
    if size == 0 {
        return Ok(None);
    }
    if binary < 32 || binary == NONE {
        return Err("effect shader section has no bounded binary offset".into());
    }
    let payload = span(
        data,
        section
            .checked_add(binary)
            .ok_or("effect binary offset overflow")?,
        size,
    )?;
    if payload.get(..8) != Some(b"BNSH\0\0\0\0") && payload.get(..4) != Some(b"FSHA") {
        return Err("effect shader is neither BNSH nor FSHA".into());
    }
    if !payload.windows(8).any(|p| p == b"BNSH\0\0\0\0") {
        return Err("effect shader container has no supported BNSH program".into());
    }
    Ok(Some((format!("{name}/shader.bnsh"), payload)))
}

/// Follow checked EFFN names/alignment and VFXB's top-level section chain. Only
/// GRSN plus its explicit GRSC child are shader carriers; textures are not kept.
pub fn shaders(data: &[u8]) -> Result<Vec<(String, &[u8])>, String> {
    span(data, 0, 16)?;
    if &data[..4] != b"EFFN" || u32_at(data, 4)? != 0x20000 {
        return Err("unsupported EFFN magic/version".into());
    }
    let effects = u16_at(data, 8)?;
    let models = u16_at(data, 10)?;
    let variants = u16_at(data, 12)?;
    let alignment = u16_at(data, 14)?;
    let mut cursor = 16 + effects * 16 + variants * 4 + models;
    span(data, 0, cursor)?;
    for _ in 0..effects + models + variants {
        let end = data
            .len()
            .min(cursor.checked_add(4097).ok_or("effect name overflow")?);
        let tail = span(data, cursor, end - cursor)?;
        let length = tail
            .iter()
            .position(|b| *b == 0)
            .ok_or("unterminated/oversized EFFN name")?;
        std::str::from_utf8(&tail[..length]).map_err(|_| "non-UTF8 EFFN name")?;
        cursor += length + 1;
    }
    // External-model-only wrappers have an explicit sentinel and end at names.
    if alignment == 0xffff {
        return if cursor == data.len() {
            Ok(Vec::new())
        } else {
            Err("external-only EFFN has unexpected trailing bytes".into())
        };
    }
    if alignment == 0 {
        return Err("invalid EFFN alignment".into());
    }
    let base = cursor
        .checked_add(0x1000)
        .ok_or("EFFN alignment overflow")?
        & !0xfff;
    let header = span(data, base, 32)?;
    if &header[..4] != b"VFXB"
        || u16_at(header, 8)? != 0x400
        || u16_at(header, 10)? != 22
        || u16_at(header, 12)? != 0xfeff
        || header[15] != 64
    {
        return Err("unsupported EFT2 header/byte order/address size".into());
    }
    let file_size = u32_at(header, 28)?;
    let block = u16_at(header, 22)?;
    if file_size < 64
        || base.checked_add(file_size) != Some(data.len())
        || block < 64
        || block % 4 != 0
    {
        return Err("EFT2 file size/section bounds mismatch".into());
    }
    let eft = span(data, base, file_size)?;
    let mut at = block;
    let mut result = Vec::new();
    let mut saw_shader = false;
    for _ in 0..4096 {
        let section = span(eft, at, 32)?;
        let next = u32_at(section, 12)?;
        match &section[..4] {
            b"GRSN" => {
                if saw_shader {
                    return Err("multiple top-level GRSN sections".into());
                }
                saw_shader = true;
                if let Some(payload) = shader_payload(eft, at, "GRSN")? {
                    result.push(payload);
                }
                let child = u32_at(section, 8)?;
                if child != NONE {
                    if child < 32 {
                        return Err("GRSC child overlaps its parent header".into());
                    }
                    let child = at.checked_add(child).ok_or("GRSC child overflow")?;
                    let child_header = span(eft, child, 32)?;
                    if &child_header[..4] != b"GRSC"
                        || u32_at(child_header, 8)? != NONE
                        || u32_at(child_header, 12)? != NONE
                    {
                        return Err("unsupported GRSC child topology".into());
                    }
                    if let Some(payload) = shader_payload(eft, child, "GRSN/GRSC")? {
                        result.push(payload);
                    }
                }
            }
            b"ESTA" | b"GRTF" | b"PRMA" | b"G3PR" | b"TRMA" => {}
            _ => return Err("unsupported EFT2 top-level section".into()),
        }
        if next == NONE {
            return Ok(result);
        }
        if next < 32 || next % 4 != 0 {
            return Err("invalid/nonadvancing EFT2 section chain".into());
        }
        at = at.checked_add(next).ok_or("EFT2 section chain overflow")?;
    }
    Err("EFT2 section count exceeds limit".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn put16(d: &mut [u8], at: usize, v: u16) {
        d[at..at + 2].copy_from_slice(&v.to_le_bytes());
    }
    fn put32(d: &mut [u8], at: usize, v: u32) {
        d[at..at + 4].copy_from_slice(&v.to_le_bytes());
    }
    fn fixture() -> Vec<u8> {
        let mut d = vec![0; 0x1100];
        d[..4].copy_from_slice(b"EFFN");
        put32(&mut d, 4, 0x20000);
        put16(&mut d, 14, 1);
        d[0x1000..0x1008].copy_from_slice(b"VFXB\0\0\0\0");
        put16(&mut d, 0x1008, 0x400);
        put16(&mut d, 0x100a, 22);
        put16(&mut d, 0x100c, 0xfeff);
        d[0x100f] = 64;
        put16(&mut d, 0x1016, 64);
        put32(&mut d, 0x101c, 256);
        d[0x1040..0x1044].copy_from_slice(b"GRSN");
        put32(&mut d, 0x1044, 16);
        put32(&mut d, 0x1048, 32);
        put32(&mut d, 0x104c, u32::MAX);
        put32(&mut d, 0x1054, 128);
        d[0x1060..0x1064].copy_from_slice(b"GRSC");
        put32(&mut d, 0x1064, 16);
        put32(&mut d, 0x1068, u32::MAX);
        put32(&mut d, 0x106c, u32::MAX);
        put32(&mut d, 0x1074, 128);
        d[0x10c0..0x10c8].copy_from_slice(b"BNSH\0\0\0\0");
        d[0x10e0..0x10e8].copy_from_slice(b"BNSH\0\0\0\0");
        d
    }
    #[test]
    fn retains_exact_graphics_and_compute_carriers() {
        let d = fixture();
        let s = shaders(&d).unwrap();
        assert_eq!(s.len(), 2);
        assert_eq!(s[0], ("GRSN/shader.bnsh".into(), &d[0x10c0..0x10d0]));
        assert_eq!(s[1], ("GRSN/GRSC/shader.bnsh".into(), &d[0x10e0..0x10f0]));
    }
    #[test]
    fn rejects_offsets_lengths_headers_and_nonadvancing_sections() {
        for (at, value) in [
            (4, 1),
            (0x101c, 1024),
            (0x104c, 0),
            (0x1054, u32::MAX),
            (0x1048, 4),
            (0x1074, 1024),
        ] {
            let mut d = fixture();
            put32(&mut d, at, value);
            assert!(shaders(&d).is_err(), "at {at:x}");
        }
        for at in [0, 0x1000, 0x100c, 0x100f, 0x1040, 0x1060, 0x10c0] {
            let mut d = fixture();
            d[at] ^= 1;
            assert!(shaders(&d).is_err(), "at {at:x}");
        }
        let d = fixture();
        for end in [0, 15, 16, 0x101f, 0x10ff] {
            assert!(shaders(&d[..end]).is_err());
        }
    }
    #[test]
    fn wrapper_tables_and_names_are_bounded_before_alignment() {
        let mut d = fixture();
        put16(&mut d, 8, 1);
        put16(&mut d, 10, 1);
        put16(&mut d, 12, 1);
        d[37..55].copy_from_slice(b"effect\0model\0bone\0");
        assert_eq!(shaders(&d).unwrap().len(), 2);
        let mut bad = d.clone();
        put16(&mut bad, 8, u16::MAX);
        assert!(shaders(&bad).is_err());
        let mut bad = d.clone();
        bad[37] = 0xff;
        assert!(shaders(&bad).is_err());
        let mut bad = d;
        bad[37..].fill(b'x');
        assert!(shaders(&bad).is_err());
    }

    #[test]
    fn fsha_carriers_retain_the_entire_original_container() {
        let mut d = fixture();
        d[0x10c0..0x10c4].copy_from_slice(b"FSHA");
        d[0x10c8..0x10d0].copy_from_slice(b"BNSH\0\0\0\0");
        let s = shaders(&d).unwrap();
        assert_eq!(s[0].1, &d[0x10c0..0x10d0]);
        d[0x10c8] = b'X';
        assert!(shaders(&d).is_err());
    }

    #[test]
    fn external_only_requires_the_explicit_sentinel_and_no_hidden_payload() {
        let mut d = vec![0; 16];
        d[..4].copy_from_slice(b"EFFN");
        put32(&mut d, 4, 0x20000);
        put16(&mut d, 14, 0xffff);
        assert!(shaders(&d).unwrap().is_empty());
        d.push(0);
        assert!(shaders(&d).is_err());
    }
}
