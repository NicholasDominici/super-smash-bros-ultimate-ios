"""Game-free SARC/layout/animation boundary tests using synthetic resources."""
import hashlib
import importlib.util
import pathlib
import struct
import sys
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("smash_aspect_ui", ROOT / "dm/tools/smash_aspect_ui.py")
ui = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ui
SPEC.loader.exec_module(ui)


def section(magic, payload):
    return magic + struct.pack("<I", len(payload) + 8) + payload


def pane(name, kind=b"pan1", pos=(0, 0, 0), size=(1920, 1080), origin=0,
         rotation=(0, 0, 0), scale=(1, 1)):
    raw = bytes((1, origin, 255, 2)) + name.encode().ljust(24, b"\0") + b"opaque!\0"
    raw += struct.pack("<10f", *pos, *rotation, *scale, *size)
    return section(kind, raw)


def layout(name, children=(), canvas=(1920, 1080)):
    raw = section(b"lyt1", b"\1\0\0\0" + struct.pack("<4f", *canvas, *canvas) + name.encode() + b"\0")
    raw += pane("RootPane", size=canvas) + section(b"pas1", b"")
    raw += b"".join(children) + section(b"pae1", b"")
    count = 4 + len(children)
    return b"FLYT\xff\xfe" + struct.pack("<HIIHH", 20, 0x09000000, len(raw) + 20, count, 0) + raw


def animation(bindings):
    """Bindings contain pane/channel/keys; generate independent Hermite tracks."""
    entries = []
    for name, channel, keys in bindings:
        track = bytes((0, channel, 2, 0)) + struct.pack("<HHI", len(keys), 0, 12)
        track += b"".join(struct.pack("<3f", *key) for key in keys)
        tag = b"FLPA\1\0\0\0" + struct.pack("<I", 12) + track
        entry = name.encode().ljust(28, b"\0") + b"\1\0\0\0" + struct.pack("<I", 36) + tag
        entries.append(entry)
    cursor = 20 + 4 * len(entries)
    offsets = []
    for entry in entries:
        offsets.append(cursor)
        cursor += len(entry)
    raw = struct.pack("<HBBHHI", 60, 1, 0, 0, len(entries), 20)
    raw += b"".join(struct.pack("<I", offset) for offset in offsets) + b"".join(entries)
    raw = section(b"pai1", raw)
    return b"FLAN\xff\xfe" + struct.pack("<HIIHH", 20, 0x09000000, len(raw) + 20, 1, 0) + raw


def sarc(entries):
    names = bytearray()
    name_offsets = []
    for name, _ in entries:
        name_offsets.append(len(names) // 4)
        names += name.encode() + b"\0"
        names += b"\0" * (-len(names) % 4)
    base = 20 + 12 + 16 * len(entries) + 8 + len(names)
    payload = (base + 15) & ~15
    content = bytearray()
    nodes = bytearray()
    for index, (_, value) in enumerate(entries):
        start = len(content)
        content += value
        nodes += struct.pack("<4I", index, 0x1000000 | name_offsets[index], start, len(content))
        content += b"\xa5" * (-len(content) % 16)
    result = b"SARC" + struct.pack("<HHIIHH", 20, 0xfeff, payload + len(content), payload, 0x100, 0)
    result += b"SFAT" + struct.pack("<HHI", 12, len(entries), 0x65) + nodes
    result += b"SFNT" + struct.pack("<HH", 8, 0) + names
    return result + b"\x5a" * (payload - len(result)) + content


def resource(primary, primary_data, *extra):
    return sarc([("info/layout.info", primary.encode() + b"\0opaque metadata\0"),
                 ("blyt/" + primary, primary_data), *extra,
                 ("timg/synthetic.bin", bytes(range(64)))])


def payload(data, name):
    member = next(member for member in ui._members(data) if member.name == name)
    return data[member.offset:member.offset + member.size]


class SmashAspectUiTests(unittest.TestCase):
    def admitted(self, data, primary):
        key = "0000000001"
        profile = (hashlib.sha256(data).hexdigest(), len(data), primary)
        return mock.patch.dict(ui._PROFILES, {key: profile}), key

    def transform(self, data, primary):
        gate, key = self.admitted(data, primary)
        with gate:
            return ui.transform_sarc(data, key)

    def test_exact_identity_gate_and_second_application(self):
        data = resource("test.bflyt", layout("test"))
        gate, key = self.admitted(data, "test.bflyt")
        with gate:
            changed, receipt = ui.transform_sarc(data, key)
            self.assertEqual(receipt["original_sha256"], hashlib.sha256(data).hexdigest())
            with self.assertRaisesRegex(ui.ResourceError, "admitted original"):
                ui.transform_sarc(changed, key)
            damaged = data[:-1] + bytes((data[-1] ^ 1,))
            with self.assertRaisesRegex(ui.ResourceError, "admitted original"):
                ui.transform_sarc(damaged, key)
            with self.assertRaisesRegex(ui.ResourceError, "immutable bytes"):
                ui.transform_sarc(bytearray(data), key)
        with self.assertRaisesRegex(ui.ResourceError, "outside"):
            ui.transform_sarc(data, "unknown")

    def test_primary_only_canvas_and_preserved_archive(self):
        child = layout("test_child", [pane("portrait", b"pic1")])
        data = resource("test.bflyt", layout("test", canvas=(1280, 720)),
                        ("blyt/test_child.bflyt", child))
        changed, receipt = self.transform(data, "test.bflyt")
        screen = ui._layout(payload(changed, "blyt/test.bflyt"))
        self.assertEqual(screen.canvas, (1280, 960))
        self.assertEqual(screen.panes["RootPane"].size, (1280, 960))
        self.assertEqual(payload(changed, "blyt/test_child.bflyt"), child)
        self.assertEqual(ui._members(data), ui._members(changed))
        self.assertEqual(payload(changed, "timg/synthetic.bin"), bytes(range(64)))
        changes = {next(x for x in ui._members(data) if x.name == row["member"]).offset + row["offset"]
                   for row in receipt["changes"]}
        allowed = {index + byte for index in changes for byte in range(4)}
        self.assertTrue(all(a == b or i in allowed for i, (a, b) in enumerate(zip(data, changed))))

    def test_all_battle_edge_groups_and_all_keys_without_slope_changes(self):
        edges = ui._EDGE_GROUPS["info_melee"]
        children = [pane(name, pos=(20 + index, 400 - index * 20, 7), size=(100, 40))
                    for index, name in enumerate(edges)]
        keys = [(0, -420, -0.0), (3, -425, 2.5), (20, -420, -3.25)]
        animated = animation([(name, 1, keys) for name in edges] + [("time", 0, keys)])
        nested = animation([("time", 1, keys)])
        data = resource("info_melee.bflyt", layout("info_melee", children),
                        ("blyt/info_melee_child.bflyt", layout("info_melee_child", [pane("time")])),
                        ("anim/info_melee_in.bflan", animated),
                        ("anim/info_melee_child_in.bflan", nested))
        changed, receipt = self.transform(data, "info_melee.bflyt")
        new_layout = ui._layout(payload(changed, "blyt/info_melee.bflyt"))
        for index, (name, delta) in enumerate(edges.items()):
            self.assertEqual(new_layout.panes[name].position, (20 + index, 400 - index * 20 + delta, 7))
        new_animation = payload(changed, "anim/info_melee_in.bflan")
        for name, channel, _, count, start, _ in ui._tracks(animated):
            delta = edges[name] if channel == 1 else 0
            for index in range(count):
                old_key = animated[start + index * 12:start + (index + 1) * 12]
                new_key = new_animation[start + index * 12:start + (index + 1) * 12]
                self.assertEqual(old_key[:4], new_key[:4])
                self.assertEqual(old_key[8:], new_key[8:])
                self.assertEqual(struct.unpack_from("<f", new_key, 4)[0], keys[index][1] + delta)
        self.assertEqual(payload(changed, "anim/info_melee_child_in.bflan"), nested)
        self.assertEqual(receipt["edge_groups"], 26)
        self.assertEqual(receipt["animation_keys"], 26 * 3)

    def test_fills_and_animated_size_use_geometric_scale(self):
        children = [pane("bg", b"pic1"), pane("blackfade", b"pic1"), pane("fade", b"pic1", origin=4, pos=(0, 540, 0)),
                    pane("mask", b"bnd1"), pane("bg_label", b"txt1"),
                    pane("set_fxui_confetti", b"bnd1"), pane("portrait", b"pic1"),
                    pane("small_bg", b"pic1", size=(100, 40))]
        animated = animation([("bg", 9, [(0, 1080, 3), (5, 540, -6)]),
                              ("fade", 1, [(0, 540, 2)])])
        data = resource("test.bflyt", layout("test", children), ("anim/test_in.bflan", animated))
        changed, receipt = self.transform(data, "test.bflyt")
        screen = ui._layout(payload(changed, "blyt/test.bflyt"))
        for name in ("bg", "blackfade", "fade", "mask"):
            self.assertEqual(screen.panes[name].size, (1920, 1440))
        self.assertEqual(screen.panes["fade"].position, (0, 720, 0))
        for name in ("bg_label", "set_fxui_confetti", "portrait"):
            self.assertEqual(screen.panes[name].size, (1920, 1080))
        self.assertEqual(screen.panes["small_bg"].size, (100, 40))
        new = payload(changed, "anim/test_in.bflan")
        tracks = list(ui._tracks(new))
        start = tracks[0][4]
        self.assertEqual(struct.unpack_from("<3f", new, start), (0, 1440, 4))
        self.assertEqual(struct.unpack_from("<3f", new, start + 12), (5, 720, -8))
        self.assertEqual(struct.unpack_from("<3f", new, tracks[1][4]), (0, 720, 2))
        self.assertEqual(receipt["full_screen_fills"], 4)

    def test_parent_origin_is_not_double_anchored(self):
        data = resource("test.bflyt", layout("test", [pane("bg", b"pic1", origin=0x44)]))
        changed, _ = self.transform(data, "test.bflyt")
        bg = ui._layout(payload(changed, "blyt/test.bflyt")).panes["bg"]
        self.assertEqual(bg.position, (0, 0, 0))
        self.assertEqual(bg.size, (1920, 1440))

    def test_rotated_background_and_named_background_layers(self):
        child = layout("test_bg", [pane("field", b"pic1", rotation=(0, 0, 90)),
                                   pane("set_rep_fighter", b"pic1")])
        data = resource("test.bflyt", layout("test"), ("blyt/test_bg.bflyt", child))
        changed, _ = self.transform(data, "test.bflyt")
        new_child = ui._layout(payload(changed, "blyt/test_bg.bflyt"))
        self.assertEqual(new_child.canvas, (1920, 1080))
        self.assertEqual(new_child.panes["RootPane"].size, (1920, 1080))
        self.assertEqual(new_child.panes["field"].size, (2560, 1440))
        self.assertEqual(new_child.panes["set_rep_fighter"].size, (1920, 1080))

    def test_unknown_relevant_curve_and_bad_ranges_fail_closed(self):
        animated = bytearray(animation([("bg", 9, [(0, 1080, 0)])]))
        start = list(ui._tracks(bytes(animated)))[0][4]
        animated[start - 10] = 1  # curve type in the preceding 12-byte track header
        data = resource("test.bflyt", layout("test", [pane("bg", b"pic1")]),
                        ("anim/test_in.bflan", bytes(animated)))
        with self.assertRaisesRegex(ui.ResourceError, "curve"):
            self.transform(data, "test.bflyt")
        damaged = bytearray(resource("test.bflyt", layout("test")))
        struct.pack_into("<I", damaged, 20 + 12 + 12, len(damaged) * 2)
        with self.assertRaisesRegex(ui.ResourceError, "bounds"):
            ui._transform(bytes(damaged), "synthetic", "test.bflyt")

    def test_primary_name_mismatch_and_unsupported_canvas(self):
        data = resource("test.bflyt", layout("test"))
        with self.assertRaisesRegex(ui.ResourceError, "identity mismatch"):
            ui._transform(data, "synthetic", "other.bflyt")
        data = resource("test.bflyt", layout("test", canvas=(800, 600)))
        with self.assertRaisesRegex(ui.ResourceError, "canvas"):
            self.transform(data, "test.bflyt")

    def test_profiles_and_explicit_screen_classes(self):
        self.assertEqual(len(ui.UI_ARCHIVES), 362)
        self.assertEqual(len({sha for sha, _, _ in ui.UI_ARCHIVES.values()}), 362)
        self.assertEqual(ui.UI_ARCHIVES["2f26ff8cc2"][2], "info_melee.bflyt")
        for group in ("info_training", "info_pause", "info_pause_camera", "result",
                      "compe_result", "standard_result", "all_battle_result", "standard_result_final"):
            self.assertIn(group, ui._EDGE_GROUPS)
        with self.assertRaises(TypeError):
            ui.UI_ARCHIVES["new"] = ("", 0, "")


if __name__ == "__main__":
    unittest.main()
