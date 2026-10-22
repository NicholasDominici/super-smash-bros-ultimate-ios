"""Exact 13.0.5 US-English UI resources for the 1920 x 1440 presentation.

This pure bytes component edits decoded SARC copies. It does not open data.arc,
load a game, change projection matrices, or deliver files. The caller must pair
it with the exact-build projection/logical-screen changes. Whole-archive SHA-256
identities admit only the surveyed original resources; a second application is
rejected. No proprietary resource payloads are distributed here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import pathlib
import re
import struct
from types import MappingProxyType
from typing import Iterator


# Bind the loaded transformation code to its exact reviewed source bytes.
_LOADED_SOURCE_SHA256 = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()

class ResourceError(ValueError):
    """The resource is unknown, modified, malformed, or outside this profile."""


@dataclass(frozen=True)
class _Member:
    name: str
    offset: int
    size: int


@dataclass(frozen=True)
class _Pane:
    name: str
    parent: str | None
    kind: bytes
    offset: int
    origin: int
    position: tuple[float, ...]
    rotation: tuple[float, ...]
    scale: tuple[float, ...]
    size: tuple[float, ...]


@dataclass(frozen=True)
class _Layout:
    endian: str
    canvas_offset: int
    canvas: tuple[float, ...]
    panes: dict[str, _Pane]


# Original decoded SARC identities, not game data. Columns: SHA-256, byte count,
# engine primary layout (the first string in info/layout.info).
_PROFILES: dict[str, tuple[str, int, str]] = {
    "250df1a9c5": ("60ac72bb76ec46c79948e7301c127359f2d0d9aac110920f20e8a83841412c1c", 2070588, "title+us_en.bflyt"),
    "254e6ddb52": ("1d32f5f989e3b1a22cc18a3abe2e040e3e483c4df419128d9244f9149291a165", 345628, "wipe.bflyt"),
    "255d184b77": ("d627bc1735683c2db19d7e09ad5795556afb68cfb2a35807e78ae9103766a3c7", 17160, "fade.bflyt"),
    "275f6c4da2": ("82894992775b22883da91063bb93b03d4e06619602218734b0dcb66ea5b74cdd", 307772, "popup.bflyt"),
    "27b55d3a3d": ("f0e11760f7a68b21da4cbad736244907537b0cabc3fb31f72652b59e4c82daae", 11063084, "result.bflyt"),
    "2a6b7ecbb3": ("e99bc82b2d9a83f6e3dcc054f9ecc369c06cfc0f03bfe869413c6a8276c103e4", 16488, "vr_fade.bflyt"),
    "2b2b9f0223": ("e6560e5e1c117fef60844ea2398f4d88ddfee900ac9282c930da6b260d907530", 7439252, "compe_bg.bflyt"),
    "2ba6c9aa0b": ("7270ed6781b04c5d6526ce3d4bf44c8ec2388628f8d5aeeca9e5675dfc954f1b", 3123520, "matchup.bflyt"),
    "2bdb1e876d": ("ac734ba97076938e378ec520c790a427cc2fbc52c5f6ab386ee561e3bd98197e", 594748, "help_top.bflyt"),
    "2bfb1f41f0": ("04ca374bd32c1e1e52d07fa5f106354eba1ada0eac7651cef82bc8de058d6484", 396504, "loading.bflyt"),
    "2bfc74d7fa": ("6832ffe0e3ea5cc0fd8093016392324de6027e2bc8a28ce2d208778c6f5ba877", 5111872, "compe_vs.bflyt"),
    "2d0e6e5ffe": ("61aa9097048f0bef17705fc75d344c759d8deccb9cfee171316cecd19823ae01", 58184864, "main_menu.bflyt"),
    "2d1be83c18": ("1cf9ef5c3d9836f3dd1232e8a287a038d37b9a790f28e9b1fbcab26250aaea54", 16444128, "rule_edit.bflyt"),
    "2d3d443a7b": ("2351f049127d9d6f154f2bd65d686392cbe4aef09b1ab4f9dbc8e69a50b95a86", 382256, "com_frame.bflyt"),
    "2d4ebc1123": ("acc8c49a71551569129d1d6e5628ccd279e059c76eaacd1f1af87439ce3d2719", 3144780, "select_bg.bflyt"),
    "2d50bcbca9": ("2ea91331ae10807101f2464eda1669d3f679d614df592e3931104df9deca686f", 665120, "stage_bgm.bflyt"),
    "2d8bafca90": ("b5330f2bcca387e49469360d2b5f4a2df25858d3b1e716807aeef1c3bd3cf4ea", 592244, "info_1on1.bflyt"),
    "2d9315c5be": ("91e1ef264e4fffb148fe4f9c7972236c877920cebe359df189d2389ab59e83d1", 79912, "info_boss.bflyt"),
    "2d97bbf8fe": ("985e83d5d2232c2fabe850065f3ad587e1d0c01760abcd5e4dea3c142d6dc6a8", 16488, "result_bg.bflyt"),
    "2d9c008b43": ("ad16dde47967d1c736557910734b5eceec94f0d64d519c56d4198df2452f94c1", 605084, "rule_item.bflyt"),
    "2db57f2c97": ("1852cd8bb99ffbaa290f2aef8e946864c2648183ed6898409e392935115ae0c7", 1244060, "local_top.bflyt"),
    "2e6a0daddb": ("779b570eecd929a4ff65d8dc87cf4aadc7cc15f3f28c9cadefcff675e9057333", 740396, "stage_bgm.bflyt"),
    "2f1277ec63": ("6611956de40bb8e5a00d7bea728d0ecb64201560a913095bdb5f1bd8e2dc2764", 3311196, "rule_stage.bflyt"),
    "2f26ff8cc2": ("c382a6e575e48102aff492fdc2bfd9c8a9cab6d9a0843b61224e4ab15e9c25c3", 2166040, "info_melee.bflyt"),
    "2f3886bdf2": ("8d369ed310ec8b3462a3d1b1763f91fd31c11f5d649b328b28c96949ff47a840", 48572, "info_pause.bflyt"),
    "2f38c6d388": ("1de2f5daeddd5abb6e8daf717108f77f679c8df1c7c9b3c3a99747cacf63cb68", 1544556, "colle_card.bflyt"),
    "2f5299234e": ("001338eed7364ac0ca14ff56dfa999252b6260294896fab8fd6dc4cea55480ae", 680748, "option_top.bflyt"),
    "2f55f1180f": ("f22dd7abe10d4d07cc74c0af054037bb481ba5cad048ba0f29b189d12ef3924b", 1652244, "online_any.bflyt"),
    "2f75229853": ("52a86f7561c88fbcab661f4bab113b105dfbce7175b6dfbb615be1c43ec88cbc", 17616848, "prize_list.bflyt"),
    "2fe6646ba0": ("b2d12d745db990e06d567dbe2d985d70556eb424d4c6e8808f3370a9af33d6ea", 93804, "info_loupe.bflyt"),
    "2fe9aecbea": ("932650e618c21dda12364a76a3f549d348a90ef0bca77aaf4dfd84d37f538d69", 54000, "info_final.bflyt"),
    "310432d388": ("26b7ac45ecb6ae6051bb39edd70482e50b8fa308e38414054e8a45613f3ac853", 1350980, "colle_movie.bflyt"),
    "3106282e51": ("f7bfd56e9c373399ade1f5ab43344b19a48aee36df11435ca50909cf3c242b17", 2008580, "amiibo_edit.bflyt"),
    "3111c836d0": ("67f0805fd50c7c8c6c4e3d5bafb0ae31df74a74d472f15ec79cbb172a21692a0", 18858220, "prize_popup.bflyt"),
    "311b13943e": ("6261506a90ad601da0dd157fc93d954de423e2a0ef3c0d30e4b834ae5006b2fb", 1441264, "rule_select.bflyt"),
    "312a83c62d": ("2a8334f453cfb61d8b306c8587293c9662a3436d589fa1b4d5d4c1610c81f588", 589532, "amiibo_read.bflyt"),
    "312c926f5e": ("d022b0f854d505cced202f8795f1db1843c3052b79624e39bf416b95c3caa649", 2691980, "spirits_set.bflyt"),
    "31312e13ab": ("bea4d259825ec6a172beedc3a0700eb635c1b18aa206d9541e50213df6dccdc6", 540800, "info_cut_in.bflyt"),
    "313cbe0d89": ("cad116655dca45c2cd6376b97b828cc1e7731b32fb37a90135c027ba2ca9b562", 203132, "pallet_menu.bflyt"),
    "3178454adf": ("3e95d772f1e617d9c2baba2fbb2ae98572a6f3bbf0155e6565888b4246e42b97", 1810220, "colle_count.bflyt"),
    "317e38232c": ("6e0b548f37f23ba839304daf4d35dc00387c792976e8238ffdd874f0ae7a4c5c", 1939940, "other_popup.bflyt"),
    "31845c7b37": ("ee2c8940adeffd2ee16e97759ce23dd8051d6af6e2f68eb14412bdeee25a871a", 15493932, "info_center+us_en.bflyt"),
    "3198d343d5": ("4c462a264afc43ee8068672084760f6b9a44bafa588bfe896492af722c66d722", 1883208, "how_to_play.bflyt"),
    "319a04e456": ("7624dc7d578dc129e93bca3f9d304ea7d505dc155419e5241dd2d8de7e91dba7", 41328, "com_bg_help.bflyt"),
    "319f3ef6b3": ("cc446e4a4aae8cbc1628b6970ea2af2b399cbb666143e8ebb8dfb519999f97eb", 2017116, "colle_popup.bflyt"),
    "31a68ae130": ("0ff5e903a18cc87190246232b136fa53b1a90a423b37f3180c660763b4e5b561", 755692, "colle_video.bflyt"),
    "31d245d743": ("004a45685bbfc3e353b44c12c8fc89fae872c27639293f3084e62f40956748ad", 215876, "info_kumite.bflyt"),
    "32e952a229": ("e9593d3cdf5dde13d7066666e807766d8619210b28987338232f663c0cf7309a", 3310316, "rule_stage2.bflyt"),
    "3310aa5c82": ("7dcc45360bd84dadffcfe8b47771f5d6b40e44468c6a54cbd3dbb6b4142eea64", 1284116, "info_waiting.bflyt"),
    "3341dbe94e": ("b65c831cac23255a7be84b75cc1afccdbc4beed967c904a055cf16c600bbe14c", 9821168, "online_watch.bflyt"),
    "334bc51f0a": ("e969679cd349396462819d0b9f438506d62ca7337cc384adbeecbc8b70d9d9d1", 23275952, "online_buddy.bflyt"),
    "334d1d711c": ("fd9c6106f316e50d65e1341e758c7bc967159e7c2df519ffeeae55fb2a5a2c1d", 910248, "colle_replay.bflyt"),
    "3350b16a9a": ("5e53371a4e0a3055c10edc1ff75a9e8f476dadb5b55f998d5c5f21b9217f65db", 16488, "com_bg_black.bflyt"),
    "335f9d670d": ("f43e5cc0f61d09564cc0aaf531eb3307d40ce3769e31ff4a00659f959e55efd5", 7369612, "stage_select.bflyt"),
    "33686d61ef": ("964a940940fdb3523d562e9d29fca9be44176fd882eed3eeb75b780668d76b5c", 2193276, "amiibo_raise.bflyt"),
    "3373b1a8b5": ("7d9afc7624f52677bdac6c9eb073a182cc092232247cf5d11d50dac69f34c56a", 5892156, "option_video.bflyt"),
    "338310ff39": ("9db87526a6c35c0c679f2e853849ae0ba6ddb3f34d5526f2c3c0c54897ca08ae", 304668, "com_bg_other.bflyt"),
    "3399c376cf": ("751fede427d5072f3c9aa0939c677f1d2abb54f0a6190bf06ad5550d1b0f4150", 4303120, "chara_select.bflyt"),
    "33a37454ac": ("339753f40effb609a4faf1921c1b4a43ca8d3dfb11137aa5fb4ca3271a92f368", 25884, "info_radar_a.bflyt"),
    "33a4789b3b": ("87e2c9db7493dc4821f9ebe49a7f76cdf17d9b0b499e1055ab4d150d4a6e86fb", 884864, "amiibo_entry.bflyt"),
    "33af85fd78": ("55d3e5bc1ac8f08337f836a95a1785ec5810d5f3bcd75ea45b717cf0c425bb65", 139384, "com_bg_local.bflyt"),
    "33b1720916": ("81710721c2721dd8d6b86f2a1e38a343b95d690e5fd40718cb0e26332e20e3ce", 8806528, "compe_result.bflyt"),
    "33b3e63b93": ("0ea848e63f4bc8b771080b9e8aac64fb35132cff2f2ab8feb357f2ba6a5276c9", 188536, "com_bg_melee.bflyt"),
    "33cf7359b3": ("acd6b3c3d4a96fa9185322d71a87c9150b012b7fb79ad83a2b9da06d38217c1c", 960796, "amiibo_write.bflyt"),
    "33d402e4f7": ("cda7a9a78121ad61f251d191b137f61c2be3daeb6c3aec46d75cd8a68edc5553", 17748320, "colle_getter.bflyt"),
    "33e107300f": ("1bd8f321a85cf8276a0794e98e2fd3f5c8e7ef5cb8194ea9a47e2ed96f7c1a57", 389692, "info_radar_b.bflyt"),
    "33f1290769": ("2d0a8180facd45c6065039b8fa867ec4e92befbc76b90c9f92840170f63a1824", 28800, "info_message.bflyt"),
    "34abdc74f3": ("298c744f2013065b549e84bdecfc64bc2469e3b95eb723530db67aee444a9c88", 283420, "info_homerun.bflyt"),
    "35000fb5c8": ("0f8ac354f0d6c4519a86dd59a56870ca409c5ecde8925f6da31ab0bee5d7886e", 29700, "anyone_count.bflyt"),
    "350126176d": ("b436f390e3de19c3fce98074bdabaf4d286f8526b31d791bed7e3a5ae8098bfa", 49496, "matchup_rule.bflyt"),
    "3509e1cc55": ("7fcb9c87b2804eaf6d7a5e6ead77a14c885d7003e721cbbc6d2de3aaf9cf454b", 2042272, "compe_matchup.bflyt"),
    "350c3e4c44": ("f4bf2ef0db472eb341d76c70f3ec770ae58598fff3f53d2aced7170fb4ebf212", 927100, "make_mii_edit.bflyt"),
    "350d896cba": ("3026e28d74f4629eed6737c9979a45265d735367ad1532931e7b079170197125", 1423900, "spirits_popup.bflyt"),
    "350f9f743b": ("1fb75735d080d4401936f5fda1ac19f873d5f051dd04adeb854e04bcba338536", 1441356, "colle_playing.bflyt"),
    "353b7ed6c2": ("7a4133b062de12d0d796ab41963eb8eaa66fc01c89c91041ac5b300febc5a740", 553104, "com_bg_online.bflyt"),
    "3541981a99": ("fae8fd16758301449880649b3fd880d164a7db34fa581c71dc472847e266aae5", 7844608, "spirits_aw_bg.bflyt"),
    "3575fbb045": ("90a8dc81751efa9d4521f836be9ccf8a134cb24af9fb5b195211e58203f9317c", 451604, "info_training.bflyt"),
    "35a2351c7c": ("4df1c2c9ffc6d8d71845fb9dc2136922b2eb88e4fb3cca55645d4dba574ec682", 81440, "info_boss_adv.bflyt"),
    "35a50a2779": ("fa2c328bef96400fcad4055c644e7ed17921f464475fe06a7ccc56d01ad9e8e5", 3642460, "spirits_board.bflyt"),
    "35c47c560f": ("b18991e9d499de95d5ef5b38016686455fff3073881b6dca0b7c2b7c150a232e", 112288, "info_testplay.bflyt"),
    "35c6cdb612": ("c28a2407de89cd28c1662c53d42effcf069b65dcae91f5a3fce4685946641fa7", 2961512, "tournament_bg.bflyt"),
    "35ce9b62c8": ("a340d5127a60133abac23ba01ea6e4cf5d114d13433c9371271a5f034ab850d8", 1869908, "colle_present.bflyt"),
    "35d719f9b1": ("7496851c4fde620b450f872eeb6dbec96fab60053c540c75d4e705fda809a9b8", 49828, "info_standard.bflyt"),
    "35df562d59": ("dfb0927ebde32782a77e5bebe6c20d26eac0f627542bf65bdfcac84d00c44ce7", 1401084, "option_online.bflyt"),
    "35f3dcfa3a": ("88be7bd20b6c37a3165fdab0fbe9d096bf2056b0ffb77059a90ba8cdc5438347", 163244, "make_mii_base.bflyt"),
    "35fa0acb25": ("d424dc13c82c6ec3530c60edd28ba35b784eeecb402dbdf0c1907fb0c2d37ae2", 41080, "com_bg_option.bflyt"),
    "35fd4513ff": ("3017f3799479c3432e4549c15afae1703ca9a70f29e23720de36ca7dbdf0f2e5", 1187968, "colle_tips_bg.bflyt"),
    "365ea14f67": ("e880c1623db24f0cee1ae382e84046beb3ea456a321b89a67dd75dbcc14817ee", 43084, "vr_rest_popup.bflyt"),
    "36de21e188": ("92047f738e16313e00bfe2d536775a77bb1080b5f3580ab6868d0ead087e1816", 7371248, "stage_select2.bflyt"),
    "37099023ac": ("4cae873ca055205658ca80fb18058948841985f4e34b9652737c6d955c48f6c3", 174324, "com_bg_spirits.bflyt"),
    "3714c2f488": ("326499e7d542fc1dbe5b547acaac4fcbe10f335aa5c841181b1a1bbf90c12b24", 6895324, "colle_shop_get.bflyt"),
    "375f417130": ("3f34f172f410023f86464884653762c4ef3869b3cc6790052085c7be1fc043c7", 561404, "make_mii_color.bflyt"),
    "377b0d2f98": ("a25819f4ea706bdbfd01dc7fd9bcf9b5fe402ccfbf20521440dab914dc21fe4c", 3782764, "colle_shop_top.bflyt"),
    "379db955b2": ("f764588225d0b45aecf80d0b72886a8040cc652a9c0d15d6bdae6be1ce95a88e", 69036, "match_waiting.bflyt"),
    "37baf75a42": ("7fde64e3fd1019b7beb7f3c915886b5e43edc22161c61dc09820af72c9650ef0", 903772, "colle_tips_top.bflyt"),
    "37cd10cd62": ("b98ea5d7557f709a10519c3838e1fd6b64c51122fe2122a5aa841896b5d1c34d", 648684, "make_mii_voice.bflyt"),
    "37ce244cc9": ("b1330c7df0023f06b14bb9c8a19a3b519306e22977930a54f531d80084f45788", 19102148, "standard_mural.bflyt"),
    "37d50d9ee7": ("30ad1d609ef2d890b03482bdfe88028ddf7a73cd5857586c8c9bab95a72aa090", 826412, "spirits_summon.bflyt"),
    "37da301aac": ("a56de16f1cf62dc4e285aac795b4ca408901b2aded20a61c34f79881ad2f977a", 1584732, "make_mii_style.bflyt"),
    "37f0e0f18f": ("b626d58e6cba5c8e9d9e9cb6893b8f73bd11041e5de9763802b415b6e49fe9c3", 885212, "help_technique.bflyt"),
    "37f34925ba": ("b18622dcb32405b3f6a8ac3a89780d3a73382e3f3775d1e74c1df8dac4f69f24", 4154652, "spirits_select.bflyt"),
    "38bacd96e6": ("f10b73416a77a30dc1ad2d7abb885e33441a03e0869a35ac70ec9ed75e000ba5", 641908, "vr_calibration.bflyt"),
    "391459062e": ("f880fc343c48790c1c44b16fb8c003d1bb05ca0645c5748e8eb670b8b1bceb26", 21401, "staff_roll_font.bflyt"),
    "392fce4443": ("971e8ac96b87bf7c81578c86c6b7d361aad8a176a82cc3acedad97fa0ea244bf", 1876012, "tournament_edit.bflyt"),
    "393637fc03": ("17525bf5fdd99183df7761e8af289e529fe0745df0642f18d77194976a972adc", 8315928, "amiibo_raise_bg.bflyt"),
    "393915b6e6": ("748e01c312c1131e2d1fe16e1aa0bf18585a81ad53b84b5921cfa9f912b54fbc", 231276, "com_sort_window.bflyt"),
    "393ce26fc5": ("c0de0fea4d9be93902d4e43d12a92ce52a4cf02c8aa9c8dd8c006c9e128915db", 477948, "info_skill_list.bflyt"),
    "396e222ec2": ("9f11604cae022a4f0131da2797db7dd4367f260fbc302b0419533925c991a40a", 2205788, "online_parallel.bflyt"),
    "397a15f3ad": ("5691d3d17425aafb6d5b46ef35d510f4012e51e9d5fdfb5fdf7c425310d71f82", 1328796, "online_room_top.bflyt"),
    "397f9478b2": ("d84d888746cfcb47b327ab671b26609836c932cb41d213376de5a37df952a64c", 530652, "online_priority.bflyt"),
    "398d8abe9b": ("6529b9e00767141b9488a8662f62659415a5b278844e65b0e7f1cc39ef487b29", 425864, "help_skill_list.bflyt"),
    "398fc65fdb": ("68288feb2a2cb6e825a27492e06a54afd39d4409669a249e229b3ad0bce051a2", 473436, "special_various.bflyt"),
    "39968c34ab": ("2571eabcbacfa398a9d4e2e63e6c991a81b9d3a68515f0d2da28b4b486fb2437", 1325388, "colle_tips_list.bflyt"),
    "39a2132b2a": ("5044c49b8eb9d93ef515887f5514700d476d71464338eeadb56c79aee4226fc3", 539564, "option_language.bflyt"),
    "39ac14cabf": ("fcef8833947572d668c8bcd602ca7152c38b15d94f523775a0e95eba60994590", 425040, "standard_result.bflyt"),
    "39d730bdfa": ("c96c1ae3474a78c0dc98c364a812cb28c4fd6f5ac4c92b80aabb0e045810c056", 2736092, "make_mii_select.bflyt"),
    "39fcfc8799": ("7530b513ab51c515aede5d8edbea32406bb65c244731d15e4adeb36f62c417d9", 1056644, "info_center_txt.bflyt"),
    "3a1b755c17": ("61f9bd23770d8e682b7c2327204c28238f910181b0f051d33336e6379a1a702e", 17700, "bp_info_gamewatch.bflyt"),
    "3acae43226": ("033d4c84b7f09182145074010a476811fccdbbb8c0dea3f6643893855c505e5e", 543296, "edit_stage_help.bflyt"),
    "3adaf18201": ("caa3964e367e41362229bd2cdc0f1925bbd394fb6a31989edc7913503e560569", 257228, "edit_stage_save.bflyt"),
    "3af589be42": ("f0ff3074f0793d4fe385800ee779c74af509d9c2c27aa3a31a466ea7293fe98c", 2525368, "edit_stage_menu.bflyt"),
    "3af82ecdb8": ("776a855a3e42310947bd8b3d5c4e25ddc608675c999ca42deb3bf7c80cb233a1", 315520, "info_melee_jack.bflyt"),
    "3b0cf76306": ("386d951ebef5122b4fc0c6a2b1cc58ee76a400e1285ff9b5c54dbac0f736a6d4", 528576, "stage_select_bgm.bflyt"),
    "3b0ed63c57": ("d76725d719c99971461cd0e709e5587a73ed797761efbaa233e175d19695b4c7", 3374156, "spirits_itemview.bflyt"),
    "3b1e6d22cc": ("aef8870ed9fbb37a3fbe6e72aa368e32a8e670a97a1e619f30e825946fb70470", 7041060, "standard_matchup.bflyt"),
    "3b2c7f8958": ("bc3e467a70d37672ed552a28c6fdc53a56355c35556a580fae0ba961c64aad78", 717452, "amiibo_subwindow.bflyt"),
    "3b341ebd51": ("7b24ead9dfc553dc913dba84aa4fc6a2500ce4d476c125e4fb7e6c5e30fd92f2", 39000, "info_result_mark.bflyt"),
    "3b516bf921": ("c7f6bf3b69bea5aaca1b4ddb791e8331f9a5c9321cc200738125470c514e9dfa", 218016, "tournament_table.bflyt"),
    "3b5b8ce560": ("67c0239650024aad477e6e5ab7a47b9f550dc834e636e011fba1cef83be17451", 1625448, "info_result_wipe.bflyt"),
    "3b6f0143b9": ("ed1092b282dc93d339cf3d85827df04e06ef8adb76dae20778ed229a308e812e", 67024, "colle_movie_play.bflyt"),
    "3ba4545276": ("68f9893577a10b83fe3e605866bf27c38844019c371c9708b5505f080cd0aaa6", 429500, "make_mii_base_bg.bflyt"),
    "3baed998b7": ("8fa2bbfb37adab06107588085654b9137a4debc390da18a0091b338e89d251b5", 7787044, "spirits_organize.bflyt"),
    "3bba4333c3": ("5b34093d118f03b08c9c8b93aaa867693502e87083fc4b4368bc60c36d792ed7", 16912, "main_menu_footer.bflyt"),
    "3bc424606f": ("58081a753e324349d770e050d1b8c0477aab3ecf58f968d01fd21874d96b0b0f", 681564, "spirits_aw_front.bflyt"),
    "3bc531526b": ("178a2daa8c08d4d8c4854e6e49a9f78164db9716f0614c6347d7ce9b7d4ed07e", 25204, "info_suddendeath.bflyt"),
    "3bceaae1ed": ("a08cdfeb460773d7000ab51b46f1a572e47f78fe0cae7cb35865ab80d4622456", 1442380, "online_room_make.bflyt"),
    "3bda7eab0b": ("5ba29f4448686d89d478b17b1d5028dda2374c3e1b66cc3ac7c0f7a6abaad945", 723436, "make_mii_special.bflyt"),
    "3bdab3a457": ("75ba9dbc2437e97ac99cda115e62bc7acf3f6c3f43e06402eb941cda1ead0c5b", 1713644, "option_melee_top.bflyt"),
    "3bed60f89c": ("ee83df5e20efb53cb06c52b4a476977d5438bfbd40d9844732c97625577308b9", 15251308, "spirits_board_vs.bflyt"),
    "3bf6841187": ("588e0a9919e57a81e0d065bc5522986b3b39165a58bc703a79d10aec307a06ac", 930772, "option_sound_top.bflyt"),
    "3bfb21ee54": ("767bb7e8e6ea78aefdd25934bf0d90b5b369a615defd738abea22d4a423e7bf9", 16488, "info_result_fade.bflyt"),
    "3c43cedbd7": ("5764a38cac5a21ddf841501523f4a51a710bd62624645ba050f7430cbed74743", 362332, "share_post_popup.bflyt"),
    "3c647f731d": ("5b1d94e6ad4164f9205dab84918cbae98d802b4dd3262bfa99ad75b0dc9876ff", 1442460, "edit_stage_setup.bflyt"),
    "3d02fdbd08": ("b551968235c46474b4bc33527844f07b1b3158353b31d9ee81575fd5d1c91c17", 11119956, "standard_continue.bflyt"),
    "3d0aa70e98": ("328d4e52215645495463318f057344b3e50f4a6e41d31aae11a834d3c2e12ffd", 36984, "info_movie_screen.bflyt"),
    "3d0e501bcc": ("a196402bf2280c535be32abc0a392abaa3bd94d67753fa879e2478c78a5fe194", 9182268, "all_battle_result.bflyt"),
    "3d16d801e2": ("b667c28b072360d90949a8b463f01878913564a0717018d99e177de4327389da", 85000, "info_movie_result.bflyt"),
    "3d2068ef4c": ("ecba588b3c53e1cb1da8cac98570d4b63a1a043701af120e60656b246987aa56", 244060, "anniversary_popup.bflyt"),
    "3d2f50bc31": ("578cf6213a829618f40110dbb1d2000024b5076c27b343a836b031be7b9e4a8f", 484968, "info_playercursor.bflyt"),
    "3d33c927d4": ("90de2db84d5ee32a3ce6f6f574a02de52655549d152a951e33d3257d72c18b36", 3785636, "spirits_raise_exp.bflyt"),
    "3d359133e0": ("89798088a56c1b8e40c274b37ac15e3b8cb17954a99cb4800ce56071b51be4c0", 601936, "spirits_aw_middle.bflyt"),
    "3d3c064949": ("14baa7f3a6c090f5785a5c88014726f7975d2a1ea033783b681b47d8ca2d4cb5", 185248, "com_bg_collection.bflyt"),
    "3d577f81f0": ("a609504449f5425203ee83257ffe7b0e02f12fc11b9b58799868e1e43524d362", 4559696, "controller_entry.bflyt"),
    "3d6357eea0": ("d3db91b0a4b37977115a1cc9827eb26d5d4e07c7cfe8c69517106dff357dd82d", 332108, "info_pause_camera.bflyt"),
    "3d707fed33": ("b912a4ce650be13a5f188303b585d6b7e7e014ee6e8eae2f9c36b8ce3d76d419", 257860, "info_testplay_mii.bflyt"),
    "3d78dd8b8c": ("6761987532a801a053671897e2ead1bd150ddd6a0d93bfb78c6453f7371f0d1e", 2672556, "local_mode_select.bflyt"),
    "3d8742de99": ("e9dab90baba6cbbc92f8dd65345b207c484c82abbf76fc0d7043441dcff3436f", 1369260, "option_button_top.bflyt"),
    "3d878ca466": ("084b1432dd4f68ee466e9a06d2e505c5616c66a7aceecc3b43aa772ab8b7e927", 16488, "standard_mural_bg.bflyt"),
    "3d8e900587": ("ca79d77bdb3d868b40e5196d1cd46a6f7b8f7bd5eb65431f85fd5c365d8c37c6", 10209952, "chara_select_base.bflyt"),
    "3da52974bf": ("bd96ec794a305cf7d5cb96dc7fa74caca5a95a6bb1be243cfad83950c3941472", 3167472, "challenger_joined.bflyt"),
    "3db5a395d9": ("770e3bfed0d9feb508100fae6ae9d00c2e8c3142ae2e277dafdfa2f78b07196d", 3108984, "com_bg_tournament.bflyt"),
    "3dc77b89ba": ("c04d756237a02963cac97508a4e49666076137ed5f00d6e619e53f50d5ef0b4e", 712284, "make_mii_hat_body.bflyt"),
    "3df660a75e": ("5ee4f521e5bd1106d272cb2244ee5677d343692b3ce05fe565c316614e3a76e0", 2726268, "colle_fighter_top.bflyt"),
    "3df83a365c": ("8a8b0ca41b4806072b582601c489e0c08ddd925692e8ef3d4edf661259289b92", 759420, "spirits_directory.bflyt"),
    "3df8e39733": ("faf60991a7521ba297deab58f8ecf9301dbb30722b96f9802f40b35645d26035", 1386108, "colle_anniversary.bflyt"),
    "3e00b806da": ("ec7fe11c3a38a23783fcf24c648b5b18d0cf06b1e07ca482bd05df5131e78b41", 218168, "edit_stage_pallet.bflyt"),
    "3e25e799b6": ("4869dd073a945452d794b35fcdedd4b6349a863015000d09d805d33de82de681", 1798252, "edit_stage_listup.bflyt"),
    "3e3802d641": ("4ade865c35ccaa72a29b13fb74d8aa3d5302c07df3cb5f4a087a753ef9df46ab", 403584, "info_result_wipe_01.bflyt"),
    "3e3b04ed3e": ("6bc779b3f738cfaed31bcb419fa4692b47eaface846214a5abde2120b30b4baf", 51704, "info_result_wipe_05.bflyt"),
    "3e490561f8": ("5410c001f6515a04b29ee6a602a8a5a396f3d62aa77811f2ce0a03829be97e77", 960316, "amiibo_trip_popup.bflyt"),
    "3e4f9c04b1": ("085f768235714692854c2a5e2351500cd216e5aecfc86e97a790b6390e0ceeef", 1102388, "info_result_wipe_02.bflyt"),
    "3ea0a1a151": ("87b1f11357ea8b91946fc66d2634ecad8d2c3330a40becb3a549cd97c775689b", 832452, "info_result_wipe_04.bflyt"),
    "3ea3a79a2e": ("296f880d439927666d3c5a2804ce6ed7b612a34362d7988e93eabb4919227fb9", 165608, "info_result_wipe_00.bflyt"),
    "3ead5249cd": ("3bce59f72d95caa242f72663ba1ce68c1f0873dbde3e6543eff65fe87dc2de61", 2338544, "online_tournament.bflyt"),
    "3ecca5faac": ("746d783425df3b539594790a05cad3dcda9d178404e77dda88466e4b6bff4b8e", 737340, "online_share_base.bflyt"),
    "3ed43948de": ("d90794e36c579aaac9e7e406bcedc6366cbb0ea8f91f6c386ff69e95f8804f77", 25588, "info_result_wipe_03.bflyt"),
    "3ee1af3551": ("6e116ad6fb2afba417ec5fa1684d8945c49601402c3e5c9f9bcdd0995c366f11", 2676724, "colle_replay_edit.bflyt"),
    "3ef06055d1": ("9053ae3f1ca465e06f026954ba68a560ea3adcded3aec6549502b9efa9cd5be0", 319628, "online_share_list.bflyt"),
    "3efe2c4748": ("83322892f93c5e9ddade24a0b224546a7bfa26829ac9917d056660658159d2c5", 206764, "spirits_set_popup.bflyt"),
    "3f1a6d9b4a": ("fab621ef2617cf067952edf9e529e805e12ee1644a63280fff32dd837732fbb1", 1310316, "online_room_search.bflyt"),
    "3f359f7e8c": ("6fadfe309c0323e5739c2eb1e782686d641ac5cc38c9dc42189f74eb1749d4fa", 516336, "online_room_detail.bflyt"),
    "3f476cbe84": ("7de4445a1eee03cd0b5bffa5fd92ad3d9df8e9d30f69ad99c8df33b04dd9e264", 2369060, "info_result_wipe_11.bflyt"),
    "3f8c418d00": ("247eb8a9d703771db4953f68880e680e9c044004bfa690fe648162bec99ab97c", 45912, "info_spirits_board.bflyt"),
    "3f9b5ccdf4": ("4010f4480930b12fbdab4ae9953ba4f6727d7501225a6f3f939515d551ccd3ba", 2433152, "tournament_bg_lenz.bflyt"),
    "3f9ea4d7fb": ("d916072a35989993ef7352c5f39e13bdd376754cb8fa8f17a16c2ad61a25c3ee", 389988, "spirits_board_slot.bflyt"),
    "3fa1931e1d": ("1866784c018ddccd83a7936a745646004d36e2834cdd02279fa357ad24598bf0", 33848, "colle_movie_screen.bflyt"),
    "3fac74814f": ("d7ab7058be7668818c923d10b832316edc2902d815dc12b97dc24cd34df0b9db", 7925088, "info_result_window.bflyt"),
    "3faeac80a7": ("3376052c427e893686f82026cf02d825672572223d07065e16324031c43102bb", 1935008, "compe_chara_select.bflyt"),
    "3fb39efa9a": ("d9f4913144ee176a8dc0294d080c31e490a92f4682ff38e14ada0a7f64506158", 373708, "colle_video_detail.bflyt"),
    "3fc9bbddde": ("ec07641f429bdf27ef01dc164c40637c70e1bd59340c86cded6ab249d615fe1c", 8561084, "tournament_opening.bflyt"),
    "3fd1fd20ca": ("baff92ebdaa3f3dd6412e8bf86129ec2c0c3fbd211985fd545f7ed7a94ed63b3", 1601420, "colle_fighter_list.bflyt"),
    "3fdcc9f2eb": ("963d440e2160870e64cc07435d45a1e48f6ae417776c79ab8e0375a53d9e02f5", 7299200, "info_result_wipe_10.bflyt"),
    "4021f162c1": ("c64d0af6b2fa922ec880bf5153f500db33eddb73b4b1087f0236baf993a182c8", 293452, "online_share_top_c.bflyt"),
    "404e9211f9": ("782361bc3fbe9e5cba77dea1e2c39afecb0e2294126491c8ee1120f53780e728", 5372716, "amiibo_result_list.bflyt"),
    "40613bbc3a": ("828e3af2279b160f10ecf69e55b86b3cb99accd4be263a88d1944485d4b18f6b", 866264, "info_homerun_order.bflyt"),
    "409651e111": ("27bf66db5bb76acf0099291d306acaf480a30246b1488a542a86605ccc1a6c57", 687436, "spirits_aw_front_2.bflyt"),
    "40b4b3c67f": ("fce1262b6f2be937b17b8393800c05798e54274b56c1cb37640bb4b24d52bdca", 296028, "online_share_top_b.bflyt"),
    "40d0052dfc": ("319ee255913e11aafae19bb5504ceb074dcf27111ffdda947f6e4b59f92f6ca9", 293052, "online_share_top_a.bflyt"),
    "411e6b1ee9": ("2ef4f2556c4a490c53f73811519e990d0e04e4ccc8e0df3a5e64616fcbe9349b", 1676972, "amiibo_raise_middle.bflyt"),
    "413e9b5662": ("2b0627c86e5eca21ff05d1af81be4d95d06da68fe55e8c22fe2e260212d81652", 1536128, "tournament_champion.bflyt"),
    "4146ea3fd1": ("4670959ed3cfb007bcc02a28b38d41087e3c27a379310c644f5780ae35ba4ec5", 2583772, "amiibo_select_color.bflyt"),
    "4147f8a0bc": ("a875bb6306cd90c46f3c1f1b0a587972ca84dee170a2c7e04737745e3217b9f2", 1305124, "spirits_summon_anim.bflyt"),
    "414e41f7e4": ("65b426dc512ec997e68b0ebc6d8b4f748d63c1861ae402890d897eacf5b1c8f5", 3489416, "rule_edit_subwindow.bflyt"),
    "41526185ef": ("56346404b1a0495f153896b34b2292403132e47f43fd48500865f77271f6d02a", 155396, "info_aurora_pokesta.bflyt"),
    "4166dae98a": ("aa3198d90cdd58dd7cd3375bf270c70c2cad042167e4b161e977b79a6053e09a", 8632588, "challenger_appeared.bflyt"),
    "416e26f809": ("adf2949beed38a332f51ad8503602a80429b3438e4c59a70af3249c269b90c8a", 910680, "colle_replay_detail.bflyt"),
    "41779f48bc": ("53eb1f85b4ed65b7974e7138581cec5e7a6b9dccd3c137dd1122c3bb24891d34", 1812436, "local_top_subwindow.bflyt"),
    "418f9f9a84": ("f54e6cacac75cd0e14f1efce940f4e7eba78f18a6aa7ef6e5e874468d9d5c91d", 781356, "colle_replay_filter.bflyt"),
    "41adecaf3a": ("976c362b53d65d745ae31b1ccc56766cb04c2fe88b4ebb7b051edfbf64250d13", 17080, "standard_matchup_bg.bflyt"),
    "41ddb7ad8b": ("a6fcb5aef58958cd401aacb339ca892bbcd81f52061b6fb536423d685a0211f0", 3552376, "standard_difficulty.bflyt"),
    "41e03b7842": ("dfa8fa014014e6336a38f45b44a78e974df7076ad1e9c79dbbf5b7be11ad51f0", 8356256, "spirits_return_anim.bflyt"),
    "4208ea30d4": ("832423825e8b74696713f127522f123d9aa9399a3a0aba0572db6b6a16a42727", 1945548, "other_popup_homerun.bflyt"),
    "422e809b4b": ("3dcac390dd5a81187f351a6217fa7dd44dd901c075d97c58db53d6497ce3f637", 286800, "info_homerun_result.bflyt"),
    "4231d5ef4f": ("2a0f9f1de026612400e1cfe8ddd36bce17602b27951b121ad66eda033128fd0e", 1273820, "amiibo_pseudo_sleep.bflyt"),
    "42dd32ab34": ("6a0616e657d546e00d88411d2ff7282bad70fe3860f3637265df217f15120ce4", 275748, "challenger_continue.bflyt"),
    "42edff6864": ("7326be9ae288a72bf30d38ea8c791e77a9a3acd91fe0d6689bd917f17ee7a680", 17372, "info_screen_capture.bflyt"),
    "42efa94c4f": ("00c50c08ffce8ce0a5082a284a7edfd568ccef1aca3ae6572699562fb40e1d92", 386396, "option_online_other.bflyt"),
    "43000f1b76": ("ca87b1533802a6115a92de373d8e36c7b0bef6768c9331e863425ddf639bc8c8", 98720, "info_testplay_option.bflyt"),
    "433ebfc1d9": ("d0a05423dbbede021b70eb8718363bb35cf11fc5dba571ecdab48b75dd19ab5f", 576508, "option_button_select.bflyt"),
    "433f6cd68c": ("ec3714485584b42039bc29c1fdc42b3f330f987ac2cb8467ee4f32e688419f1f", 24896, "info_appeal_palutena.bflyt"),
    "435f56443d": ("a557f74fc992d353bc3039f7bbb95a110d656dd9b22fd46bdcc3bd854ebe1639", 24704, "prize_list_subwindow.bflyt"),
    "4366792c99": ("0442d7c356e170def60f867b3dc97871f74ec70041207929256268e6160bc237", 9714804, "info_aurora_punchout.bflyt"),
    "436fdca0fb": ("a2bffb0109c11c3a336ad9eaade65a9a62ffa24a0e3ad636739ee43f803b3700", 39772, "info_movie_recording.bflyt"),
    "4378fcac41": ("0c3933aa5cd211c35f20b0b1178154fc25b26b90be0aaaf50ba9b93e64525141", 3113276, "spirits_campaign_top.bflyt"),
    "4386fef4f2": ("5f11fffd0116908a60043008a74ce5661014fac5d5313bb38f7d8758593de26c", 3403700, "spirits_campaign_gym.bflyt"),
    "43a1bce805": ("031b54b33feb23f5aeb779580646d89427b113ffb36aa7147715191c98a83dd0", 1985524, "colle_sound_test_top.bflyt"),
    "43b0f7ba88": ("bc741d18846b72d7d7110e42cb6283877c572ec53f28bc7f3a90a42c0a60099b", 62272, "info_standard_ending.bflyt"),
    "43d97493d8": ("13eb2128d5e7800252393c8d802a9e56e9a53365d7ddd94ac80f798586264785", 29380, "info_assist_tvgame15.bflyt"),
    "43fa4398b0": ("1c395fbee3f54e10a599020ee1eae32b68dbbbf38e7260e34434deda4250ea2e", 230280, "colle_playing_report.bflyt"),
    "441336e080": ("9b1a594a785543237d99f450bfdf3736ee7cb2856f2a6c8ff488b3ae87d8cc19", 2961512, "online_tournament_bg.bflyt"),
    "4476569044": ("eda510635964b568efe8d8f94cce4fe0fbcd2fe6387592c53882fae3d53b92c4", 2084540, "edit_stage_subwindow.bflyt"),
    "448c3b5047": ("c19316453dfae18a3a0027d7eca4423cc467e9efa295ebc5cca1379977fd80e3", 45184, "share_post_thumbnail.bflyt"),
    "44cdb100d1": ("131b11f9c3159bfb80b9550eb8bf0f0ac71937258bc3936756fa2f8136695214", 69752, "spirits_staff_roll_font.bflyt"),
    "44e152f14f": ("35fda06bd41ea426c877c75c80951a080d379ec3422092f4cd0b3cbbb4129be8", 3111804, "amiibo_result_detail.bflyt"),
    "44f2b848ee": ("92f99fa45ae7f343c0c9d310e0af25ed28020d2a01d26a815bbe981e5f4fc520", 44300, "chara_select_homerun.bflyt"),
    "44f4a0013f": ("ebbe65abadce57fee30d56b240e6518b3cd03c4aed79cbb15a2c3d7050b8f094", 87896, "online_share_capture.bflyt"),
    "45148b3c3f": ("8721dc72e121c8769b59919d1849293516484269518e7d8a019a300984f4e169", 11645912, "spirits_board_rule_bg.bflyt"),
    "452703a0eb": ("c3cbbe35cb0fbb369e263361e2118e188dc35fb403306ddf07c3d77956e5ca63", 848764, "chara_select_standard.bflyt"),
    "452dd70eac": ("11bea750bb9e15b6dd9cf6d0caa0016d5f66e5639129433b18ea4003ff8c5117", 649160, "standard_result_final.bflyt"),
    "453da8ae7c": ("882ff58cb4968125083efd0d9ea9bd55ea4eb46164534988c8c535548f05c9f2", 2014652, "spirits_campaign_menu.bflyt"),
    "454365a87b": ("37543f9119495aa0246bb48f7d86405d5c90e65e5e0aa9bf6f584551eef27a2c", 75444, "info_stage_streetpass.bflyt"),
    "45452b661d": ("09eb70a393a5c82c93c8ca2e92f93e33a34e9431f62331272677c5a2f40443cb", 760, "info_stage_pictochat2.bflyt"),
    "456265477d": ("8e9234a05c19dbd6f03bbdee72cada057e08ca54cd0f87027e0252b22851b187", 330408, "info_appeal_metalgear+us_en.bflyt"),
    "4567472f56": ("b0a1a1499768d30266a5ec916377f9293788e34c6b9a9a5f4b6cfb96aad4302c", 7695140, "spirits_campaign_info.bflyt"),
    "458e89612b": ("8bc68797e4812f8979c70225632c51dd16e0ac94b2ff7836ea45977e06d1b32c", 650436, "online_room_subwindow.bflyt"),
    "45a14ead0b": ("d73fc7e95e928898efc00ca8fe72a5128f8ed01f5fe32e840221c91ea5e46d26", 17476, "info_result_wipe_nocontest.bflyt"),
    "45c8bb4781": ("31d989e986a23f04d5306b2b147ae9c9665d0ca64e03adbd7e81432b8c1a9bde", 6687620, "spirits_campaign_shop.bflyt"),
    "4610b6a1e5": ("3df4e8ec425bc0aec191303fa8ebec4cc731660665c8c4b34dd7df6788bf65c7", 5853340, "online_watch_shop_get.bflyt"),
    "4649a1bf3f": ("09e6c03a43bc4fdee695aba07a37d1752f55c8612a2a247658c9a0172bffeaaa", 8059600, "spirits_board_special.bflyt"),
    "46aa9c30a5": ("b1797bb578bd1216f23b99cccb88ec0b5a4e737265bf3b943daf5cb8650333e8", 6096636, "online_watch_shop_top.bflyt"),
    "4711f69ee5": ("e2fe5e6f76ccafbe28625fb79821ca14fc874158eb348f677b2ba7504170dcf7", 350924, "option_online_shortmsg.bflyt"),
    "4734f2e022": ("5229ebdb339dffdfd53e10760e7b620d0204eb3816ea3740e215b76f57d0348b", 2961512, "spirits_summon_anim_bg.bflyt"),
    "4738b237b3": ("bd88d899157ecd57c684f25bc229877910b5dc4307dd7ca8514b7aa632a81b9f", 47760, "spirits_campaign_movie+us.bflyt"),
    "4763b2296e": ("079badfbe4dfa01fc18ea7991b9c84f739fd400e4684c29cce2b67f1eaa6bd90", 295040, "info_playercursor_item.bflyt"),
    "47709fa93f": ("6ace47dab6de1a97f64da7aeda909a322ff3f14fe9d3f0e978f1653743e5c577", 25416, "tournament_edit_figure.bflyt"),
    "4789f3c551": ("1b5a11acb1c04f4c807642e231a57551db3253cba398de1360202a1034c6f1df", 2453764, "spirits_set_edit_front.bflyt"),
    "47980de932": ("00a1f730a67c2546305f5900149ea8e1af3c348e1103e6343314bda28e9fcbf2", 389900, "online_buddy_subwindow.bflyt"),
    "479dc7e274": ("7f3e3956e00f03d160b6f0575acc2dd63c57c059b29ee9816ccfef4076aadc21", 129884, "option_online_colorpop.bflyt"),
    "479f15c45c": ("35cc8118f833c087cc4927170aaddfc2353aae55a374a4337d0a3b15352e895e", 386712, "colle_replay_subwindow.bflyt"),
    "47bed0a29e": ("bea510e888faf296668512bc438ef31e095878657be46fbcd8aecf0dd214b8c6", 639484, "option_online_oppo_tag.bflyt"),
    "47eb02034f": ("6a9d47b3ab27bebaf15c27bc9eeea4596588983261a1344db8f3d3565d739757", 10663896, "spirits_campaign_skill.bflyt"),
    "47f4497116": ("0db022fecc7b3bede0d6e196233b8ce5abd60f021ffc9c66ad8efa4273309075", 288532, "colle_sound_test_voice.bflyt"),
    "47fba52e05": ("0aaac562bcfbe5fbc52462cf488647575c9ac850a8c48ae01a6f929b4662a9b4", 3109372, "spirits_campaign_event.bflyt"),
    "4801f37a9e": ("3d1da6af0ac3975ba2ce9879264876ae60568887dddd1881c3d505240aaffa82", 849504, "online_share_subwindow.bflyt"),
    "48a2c514bc": ("150aa0c652587d609ff301f608f77f9622eef9199060a332a03a5ebcc8649d2e", 1327564, "online_competition_top.bflyt"),
    "48de88ba51": ("f362e401612c8c0c81976a08a0a935ecdfe1f2683e26d19a39ee3957d3243501", 1145836, "colle_replay_edit_save.bflyt"),
    "4903b52dc2": ("ad6e3283a5dfbd6a8e61b37225ad262afd31e0bbbf050c587aedb34fd57ebeeb", 3434404, "spirits_campaign_search.bflyt"),
    "491dea2f10": ("1350c221d0846985c4f8b735dda1b2a56af55eca7dcb70f7b403540dd9a6648d", 290164, "colle_sound_test_series.bflyt"),
    "4932c70acc": ("dbaf506aedaa12a404c9d809b7d1caa819dc2135000edc3fc987c94ce5ca7f19", 3446500, "spirits_campaign_school.bflyt"),
    "49335f878d": ("4d52eb38705e8297a4dfbed87b020971af06ddc088a313182f5a1570e3f9caa8", 341744, "chara_select_tournament.bflyt"),
    "49369b22ed": ("0c30d6d12ae750939dd6101af95a33ab1fd659a62b745fb4a99e8dc3e994f0ca", 877956, "colle_present_subwindow.bflyt"),
    "493fc894a1": ("191581c5a9f840fb510435c790b4faa0c157c74f34b71a33ccf864924eb0211f", 174028, "online_buddy_startwatch.bflyt"),
    "4943f49a02": ("6c94d9d59103d2d698f5a2f142739703cab4a44827f6362abb0219b0d94ed14b", 3749536, "spirits_board_set_front.bflyt"),
    "49595ec70a": ("367986c01baa030d2b25ea121b3d40f34209a433702b1c6c0fd9ab1560b6bf67", 208812, "tournament_edit_confirm.bflyt"),
    "495fd95785": ("b4d8f232c8391e5a8dda1f9f593fe6415a1594b577d5d81adcfa6ba570f7ddfc", 2207420, "spirits_raise_subwindow.bflyt"),
    "49a71bdcca": ("e0b7f074f1320a82eeb034c5dc71d1d43aa738f0c67707cfc1560ae64959bc6d", 1329404, "option_button_subwindow.bflyt"),
    "49cd92cf70": ("9467a867b4b8b0de64477831db792d481ef619581c1a27b47f253f3a40a79363", 1441372, "colle_sound_test_player.bflyt"),
    "49e1642d97": ("337f20b0d7a0e427c4ccf96e7181e10ab9afb9692c7038ef30919c86fefd205e", 1395408, "online_room_search_list.bflyt"),
    "49fdb49b23": ("de118224cef1d93706359bb595bb6c6556e0162f4df4f6f8c05f3d7a9222e4ce", 3624704, "compe_chara_select_base.bflyt"),
    "4a1ae2c5a8": ("9ea6fd7bb98fcbd4d9c3b12062b4f99506fb7144c48d3908b4c8d1c04c06b931", 216076, "spirits_set_sort_window.bflyt"),
    "4a63c310ba": ("77edde3bc2ed792b832176d9ecc79a57ae3212bb9de3ac4c609d225669bc2b28", 1645228, "colle_replay_edit_asset.bflyt"),
    "4a771f3646": ("87b1a52f7a668aad2755a2e224f42815bbd66e18d0d33a0c828e15c988ed281a", 241084, "online_share_save_popup.bflyt"),
    "4a7ee45c24": ("c862fa59a5078e1f64156429f2df3faff8b34c34686aa9f2546fb5d30ba52cd9", 312740, "online_tournament_panel.bflyt"),
    "4ae8252885": ("539e69ea9f5afebbf031ab806481783bc7a269f2dab4b6c477a6c14cf10eef8c", 1131360, "info_waiting_tournament.bflyt"),
    "4b05fa11e0": ("de5e9e005b195a27977bf7d357c229c2461344ba21ec64657a2ee40bd0ecd7dd", 506460, "tournament_table_overall.bflyt"),
    "4b065a9f13": ("7eaf2ae1f145295b6a770c34b2ab6df38d0efcdde5c39bd9755a038a712375f5", 16488, "tournament_champion_back.bflyt"),
    "4b1cde7800": ("81c4a9cfce9271ce85a5e7cf6efdb77296730e4f11128d997ba22fbd3b4cb4f3", 1189140, "spirits_campaign_staging.bflyt"),
    "4b1d14344d": ("fad6a000f3b9574d576d510086f22dc0bc96d2526d4a94f1276ece5a31ed6fca", 3206368, "spirits_board_rule_front.bflyt"),
    "4b3edaf864": ("7eafad02f5b02a8bfe898b5c3d7430cdbbfd319f6618eb98cad8b645da74d3d3", 1791404, "spirits_return_subwindow.bflyt"),
    "4b74330ddf": ("a2fae03f7e7d59311b0aa46a9597ee6b9308a0bbf16859c48d151bd7f8865fa1", 444548, "spirits_raise_super_anim.bflyt"),
    "4b916b03cd": ("641a7a5d455f1e9a092b70a5cd3b82f857e36ff03c403104616a36a83835b494", 3577088, "option_button_controller.bflyt"),
    "4b99b6925c": ("ba154636007a8d290f20845bc4663f31df93c931aef88ec226b74cb20fd0ff85", 1318332, "spirits_summon_subwindow.bflyt"),
    "4cab523283": ("4fdbaaaf6212ef1d3263b9644fdc7fabc2634204a040c5e1b9cc59155fdeb0ed", 55116, "online_tournament_replay.bflyt"),
    "4cd49feead": ("cb7c60ea3f80e9a5b34a6678fd1566b9c19e26ba66220a3c3ea31ed9cbff8c52", 2153596, "colle_replay_edit_tellop.bflyt"),
    "4cd8f28383": ("b33a7db0b9bdba0f4caf429a7f4fe6ce4ec5c62b8cb266289bf8fb37246ed99e", 16488, "colle_replay_edit_rights.bflyt"),
    "4ce88c921c": ("f0a01cdc0f5655952c7bab99d57437d9c005eecc3fc8b3516410c529bf9e1a35", 3057316, "online_tournament_center.bflyt"),
    "4d07360250": ("ebb16456bd8abe35b70c2b5ddccbda873b3724032f2e9d18832b6a0a4913832b", 16488, "info_stage_mario_newbros2.bflyt"),
    "4d08ba44cc": ("c5342e42e1a8cf080db8f0bbe2438265c1422099f292f58cbd5f4655243e150a", 4469420, "online_tournament_table_04.bflyt"),
    "4d0c9b0fc1": ("823bd0c80cc65e70530cc6e53eef9e6ac02c90121ea033f6d43ec68d95b94c8d", 6174620, "spirits_summon_edit_front.bflyt"),
    "4d0db0094d": ("b68eed139510fa5c495dda58fb3f0ef94f901203f1a1ac41a28fc5db377cf80b", 4665232, "online_tournament_table_08.bflyt"),
    "4d13a2120e": ("a714f8cd184be4c470cba9d2aa57d791499f5fe4af90fdd02c07704b51ee036e", 430688, "colle_sound_test_playlist.bflyt"),
    "4d377d8b90": ("c17fe420297780cc110f2a16b545bdf554497220c41a645a7534dff76b3a64c5", 274980, "spirits_campaign_continue.bflyt"),
    "4d489a29f7": ("fe31740dce7101579632a37a5d823bca10e3da5ff29d5a4d08e5c6bf537f84c0", 82176, "info_spirits_board_result.bflyt"),
    "4d7c22ad43": ("db546ca787682fd967a31181dbb0ac7223765057af1cb4919bd8e964128f3d43", 4756476, "online_tournament_table_03.bflyt"),
    "4d7f24963c": ("30592e5aaeb8348243c661c93cbe76e2b0700770179376aea771e2e13a8614dc", 4773404, "online_tournament_table_07.bflyt"),
    "4d901933dc": ("e0978a4c5b06440956e5ca6c8b6ce2692d0b57ad7eaaefd984ab567352a51c83", 4530236, "online_tournament_table_01.bflyt"),
    "4d931f08a3": ("6db2a8c4dbcd84778a4feeccd4baca19c4c4aa20583c3b127064c825c7dc9a5f", 4538428, "online_tournament_table_05.bflyt"),
    "4d96154522": ("9b2600d5cac3faea58721bc6ec54556163302172b92f1e8b591bf832dcdbc805", 4673968, "online_tournament_table_09.bflyt"),
    "4dcde6f58f": ("4afe84a597c98f824752144e7348ce129c44d4322fb23981f033f5c362f41f37", 4877904, "spirits_campaign_facility.bflyt"),
    "4dd62aa636": ("3fe1520e6b993670c66610222683e801fcc946d197e84ce8511792cef8500a6f", 4681616, "online_tournament_table_10.bflyt"),
    "4de481da53": ("7da3a41c00c891e95de8a01d0b3c1d0683353be89c24745c0e5867b7f0e14297", 4480156, "online_tournament_table_06.bflyt"),
    "4de76d7d78": ("61123ddc7f7efbad8f1e5bedc10ec4c59e547a7d04a5b2b645919b8efd1848f5", 2236588, "spirits_campaign_menu_etc.bflyt"),
    "4de787e12c": ("a9d8ee11b86d5f7ef82e0b8cdc11a63f1988e401224fd7b97d9a3863df4c17af", 4465868, "online_tournament_table_02.bflyt"),
    "4df41442c6": ("1d712600a87d7382f8ac726c256d3a3e5a0ecd8decbaec271d90fa5a4f31a052", 581756, "online_parallel_subwindow.bflyt"),
    "4e4756720b": ("6754d8870b4882d4bd286702dbe4d3b594b72506ca797cefc6901cfb2c32b3b7", 1623324, "colle_replay_edit_project.bflyt"),
    "4e5d97a91a": ("d2c341210502e5f9d9a6a8df41dc75f16b3cfe9014909c6074cb44a6d0aaa0ca", 2437248, "online_tournament_bg_lenz.bflyt"),
    "4ec389037c": ("28036a9b82ba0f47e22818a27fb81f23d8ba4abe21e0a3406115798cdd35fdee", 718288, "online_share_search_popup.bflyt"),
    "4f3c72ccda": ("9f4cca3231ef7fb6b61b197b671c414f9a25179369a532c792a71de880da94da", 143264, "online_tournament_panel_team.bflyt"),
    "4f74162dca": ("379c2ed912818bc53fc2bab40edcd13f4fed3807b02b82bc4e3ffe5009dbbd8d", 649900, "spirits_campaign_subwindow.bflyt"),
    "4f8a07adb9": ("a978f728fa58fde1fc203a912f4febef97551fb9a4df0b835b8e5dfa89eba32b", 2070828, "colle_sound_test_subwindow.bflyt"),
    "4f9662039c": ("27e83ecc52e9bb4e20a4766767df7e5e4f85a7fdee222d8257a2648687123ddf", 1687660, "info_appeal_starfox_cruise+us_en.bflyt"),
    "4f9b5db6c0": ("7ce43e9ef0f172ef69b03aa19ce11a50002cd3ddd99400a671f115ccb5644fe9", 303628, "make_mii_special_subwindow.bflyt"),
    "4fe8f3fdfb": ("bbc033062a0f42a3d7013d2a9b22411aee616292b2e981a88a3dc416daf3a171", 697040, "info_appeal_starfox_planet+us_en.bflyt"),
    "4fed728efb": ("0bcfecde49318eec94e06919541e78639ea3d98ab1314706489c2386e8a39f84", 7944548, "spirits_campaign_search_in.bflyt"),
    "50b9b705a3": ("d7086fb1a0b2ebf605eaed1d99f7aa2e37ce7eb2d4e1987a12155539aaa2ac34", 3994036, "online_tournament_champion.bflyt"),
    "50edc40603": ("29e02343b1af21871c0dfeda6dd7bec254089bdc25895475b4020a31bfee9c6f", 1151452, "online_tournament_entrance.bflyt"),
    "512245379c": ("9aa0fd0889821be6b93511890e32b0a86f59f97fda542f2c09fd9b3b00c6b105", 664620, "spirits_campaign_map_symbol.bflyt"),
    "51d70335cd": ("3d495d4106b5471568e016fd4dfa25f8eebea4e527b0150b0ba75890d4f1bda3", 236476, "option_online_fightericnpop.bflyt"),
    "52108de542": ("f2c1380aaad053e35620302fdcb0e55723d54da9ce5275d74ee62da5bad35e6c", 6100012, "spirits_board_special_bg_10.bflyt"),
    "5211ed724e": ("65cb22343237731d264a52a79ce5454ab71c35bff2ac079afc8b8fa80e2bf9b4", 7357540, "spirits_board_special_bg_01.bflyt"),
    "52250cac66": ("36953b66347726f978c14c94b6115933c92b1e93efbe00ab444755bdf4bd99cd", 4693788, "spirits_board_special_bg_00.bflyt"),
    "5235e85210": ("b1406b491d1ef3a9a6bbc719b4235308e0daa272d5b2b4f0acdea266ac4c1eda", 3377872, "spirits_board_special_front.bflyt"),
    "524ccf1036": ("ed5a90704fdd11f3f3ae91bb070e8a131c6e3a104078b302af77730b246ec24b", 6555608, "spirits_board_special_bg_02.bflyt"),
    "5259735b67": ("04a86beadedea9232013727303d205db98c03f06b72471d0fbc0d9bcc6820512", 6713564, "spirits_board_special_bg_08.bflyt"),
    "526d92854f": ("cbaf3588b9852308696e82ca399ea5ba633bd2f4fab79427bdd64a68e5f60012", 5785864, "spirits_board_special_bg_09.bflyt"),
    "52782ece1e": ("a01647c9a35d8441a695ebbad2a35170e566af3b92433c0e2ef9ee446d137d68", 544896, "spirits_board_special_bg_03.bflyt"),
    "529ba62cd9": ("97f0247fd60972823ded29a2bc71c373ab278568f337ed03617e3ed63ce6ca2a", 6203484, "spirits_board_special_popup.bflyt"),
    "529e45f90c": ("cd1626f34d1e7480a676a219a9645359fde98b9d90cf1fcb8f57cbbac2c26ed4", 42620, "colle_replay_edit_recording.bflyt"),
    "529f486896": ("8201144f5c9de84b39cd4a7a1a018329d8af5e02a2cb05c5106c64dc74eb0504", 9752472, "spirits_board_special_bg_06.bflyt"),
    "52aba9b6be": ("d819fe442d6ed707e162b0445693eeb1996bf5fc3bd09d4c50791eb5f2c20587", 8769320, "spirits_board_special_bg_07.bflyt"),
    "52b2512ee8": ("2be84d461b12c097658d22afdf3d1bb2de260d3ff65be5f6ca0f208e1e959d1f", 617092, "online_share_playing_report.bflyt"),
    "52c26a0aee": ("13190ca6ae4197ff4421af8b649638a4c6bc871f8e89a630c7f910d43c086ef2", 5017620, "spirits_board_special_bg_05.bflyt"),
    "52f68bd4c6": ("73f73f91d89047403e6db3c25c23cfbc998cc33049a1a4bc366adda7e8ba0734", 3012080, "spirits_board_special_bg_04.bflyt"),
    "534da69c80": ("af6320fd69e2f44b1885c5a8bd6a34a6d5cc00e65e03d7c527b07e4b5afe3a74", 1241004, "colle_fighter_list_subwindow.bflyt"),
    "5369b5e37e": ("5bd8e93eafb1c422da19c4dbaea9c9c313193a09494e587b3ad18d14c84e7a0b", 303756, "option_online_shortmsg_popup.bflyt"),
    "539d438a2d": ("e62572e47b5dcb55c6836a0bbe7cd3e2d6ab188c60a48b671e4f870114bb3366", 16748, "spirits_campaign_facility_bg.bflyt"),
    "53d17467ca": ("2d7acd6846f719330d281d1ed4d505d2bd71bb6dbfc6c5a03f19cf50f98e08d5", 1550988, "spirits_board_item_subwindow.bflyt"),
    "53ddfc83e5": ("7ccbc55ca223d7668788cfce93cd48e277d1ec18831c8c2e0618a224acec401a", 21812, "online_tournament_replay_cursor.bflyt"),
    "548788c82c": ("cbf73e8f5e3c06f6dd7652266da97ce5f601e95475e3bcc3db662273481b72e7", 2171836, "colle_replay_edit_transition.bflyt"),
    "54c5bb333d": ("9905bddc9ff9c9880d69d88f8930bf6388eea1925bb1485178a7c0aef1124606", 54344, "chara_select_online_official.bflyt"),
    "5563f03110": ("e54efbeafd24703dabd53f50cade2b22d24ecfb5aff608952e22009c81e9d8f7", 4051252, "online_tournament_champion_team.bflyt"),
    "55a3c772f1": ("39263e370980e1bca97594c8ccd5a4b0d5e5057406af9f62e7c5fd630a6c6681", 574892, "standard_difficulty_subwindow.bflyt"),
    "578978b603": ("1316b53bd6bab9197e43f8c1239e82ae31787aea0b29ae2454d62b72399c5dea", 280876, "colle_playing_report_subwindow.bflyt"),
    "57eb43ce08": ("3b5f688d8935f5b2c7d7a78e12fce25ef1ccc89ae4dfb312bbb9832dc500be26", 4010556, "spirits_campaign_facility_shop.bflyt"),
    "57f9f05b13": ("3aa4a31e8caf2ff7dcf3d4ac246e25a67cbaca3c371fa960b9c2417703157b22", 584188, "spirits_select_style_subwindow.bflyt"),
    "58b7130393": ("8ec0a3eb3f219cdec841482f4be6234f84931a94948c9d536bba4a2a4d246a3b", 190552, "chara_select_online_tournament.bflyt"),
    "59b49dd6a9": ("e96c12f94ae1b044b653e20d2a870e409e57278c547d70ee646576e1cd244988", 478092, "spirits_select_filter_subwindow.bflyt"),
    "5acfa31190": ("c84d6c81676f6721726e9611eceef2e7bcf9888e492c3ef7f0507a806be1c0d7", 16504, "online_tournament_champion_back.bflyt"),
    "5d9ec02d38": ("d0c7dc567ef8f144b3f605f4c6f279d74f6b59c4257b4395a3ff4e06a352b489", 76136, "spirits_campaign_school_subwindow.bflyt"),
    "6081935383": ("e7c5d7d3f63c86a2b7c5f7a67151d1f9176f6a88bcfa8a8f3da15456d4f81dd9", 933648, "colle_replay_edit_recording_target.bflyt"),
    "644456d2cc": ("39239257fa749c35984c0e7012c091415c210072b1c90a6ce8a27fb341b84898", 852568, "online_tournament_champion_offscreen.bflyt"),
    "66d690d369": ("55fdc452640e1f954370a222e40386ccb888b1321c759abb69c21a1bae699aa6", 278052, "online_share_playing_report_subwindow.bflyt"),
}
UI_ARCHIVES = MappingProxyType(_PROFILES)

# Explicit ancestor groups: moving an ancestor also moves its descendants.
# Never insert a new pane: game lookup/index assumptions stay unchanged.
_EDGE_GROUPS: dict[str, dict[str, float]] = {
    "info_melee": {
        **dict.fromkeys(("time", "bgm", "title_special", "set_parts_enemy_01",
                         "set_parts_gsp"), 180.0),
        **{f"set_rep_stock_{i:02}": 180.0 for i in range(1, 9)},
        **{f"p{i}": -180.0 for i in range(1, 9)},
        **{f"p{i}_2": -180.0 for i in range(1, 5)},
        "sandbag": -180.0,
    },
    "info_training": {
        **dict.fromkeys(("status_R", "btn_finish", "hit_finish", "camera",
                         "L_staying_func", "btn_finish_cursor"), 180.0),
        "L_staying_help": -180.0,
    },
    "info_pause": {"set_parts_title": 180.0},
    "info_pause_camera": {
        **dict.fromkeys(("button", "set_btn1_05", "txt_man_end_bg", "txt_man_end"), 180.0),
    },
    "result": {"info_sub": -180.0},
    "compe_result": {"set_part_help": -180.0},
    "standard_result": {"title_anim": 180.0, "key_help_anim": -180.0},
    "all_battle_result": {
        "player_symbol_nul_00": 180.0,
        **dict.fromkeys(("set_part_result_help_c", "set_part_result_help_r",
                         "set_part_result_help_c_d", "set_part_result_help_r_d"), -180.0),
    },
    "standard_result_final": {"difficulty": 180.0, "value": -180.0,
                              "keyhelp": -180.0, "set_parts_ticket_up": -180.0},
}
# Other menu/pause/results content remains centered at authored size. Only the
# above named groups move. Full-screen fills are selected separately below.
_FILL_NAME = re.compile(
    r"(?:^|_)(?:bg|bk|black|white|blk|fade(?:out)?|filter|mask|cutout|screen|overlay|color|gradation)(?:_|$)"
)
# Full-screen overlay names without the usual underscore-delimited tokens.
_EXTRA_FILL_NAMES = {"blackfade", "com_white8", "wipe_bl", "noise_tex", "flash"}
_FILL_LAYOUT = re.compile(r"(?:^|_)(?:bg|background|fade|wipe|transition)(?:_|$)")
_CONTENT_CAPTURE = re.compile(r"(?:^|_)(?:fighter|chara|player|movie|cap|image|icon|symbol)(?:_|$)")
_PANE_KINDS = {b"pan1", b"pic1", b"txt1", b"prt1", b"wnd1", b"bnd1", b"scr1"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ResourceError(message)


def _unpack(data: bytes, endian: str, fmt: str, offset: int, end: int | None = None) -> tuple:
    limit = len(data) if end is None else end
    _require(0 <= offset <= limit - struct.calcsize(endian + fmt), "field outside resource section")
    return struct.unpack_from(endian + fmt, data, offset)


def _string(data: bytes, start: int, end: int) -> str:
    _require(0 <= start < end <= len(data), "string outside resource")
    zero = data.find(b"\0", start, end)
    _require(zero >= 0, "unterminated resource string")
    try:
        return data[start:zero].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResourceError("invalid resource string") from error


def _fixed_string(data: bytes, start: int, end: int) -> str:
    """Read an inline name that may occupy its entire fixed-width field."""
    _require(0 <= start < end <= len(data), "fixed string outside resource")
    try:
        return data[start:end].split(b"\0", 1)[0].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ResourceError("invalid fixed resource string") from error


def _endian(data: bytes, offset: int) -> str:
    bom = data[offset:offset + 2]
    _require(bom in (b"\xff\xfe", b"\xfe\xff"), "invalid byte order mark")
    return "<" if bom == b"\xff\xfe" else ">"


def _members(data: bytes) -> list[_Member]:
    _require(len(data) >= 20 and data[:4] == b"SARC", "expected decoded SARC")
    endian = _endian(data, 6)
    header = _unpack(data, endian, "H", 4)[0]
    size, payload = _unpack(data, endian, "II", 8)
    _require(size == len(data) and 20 <= header <= payload <= size, "invalid SARC bounds")
    _require(data[header:header + 4] == b"SFAT", "missing SFAT")
    fat_size, count = _unpack(data, endian, "HH", header + 4)
    _require(fat_size == 12, "unknown SFAT header")
    nodes = header + fat_size
    sfnt = nodes + 16 * count
    _require(sfnt + 8 <= payload and data[sfnt:sfnt + 4] == b"SFNT", "missing SFNT")
    _require(_unpack(data, endian, "H", sfnt + 4)[0] == 8, "unknown SFNT header")
    names = sfnt + 8
    result: list[_Member] = []
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []
    for index in range(count):
        row = nodes + 16 * index
        attr, start, end = _unpack(data, endian, "III", row + 4, sfnt)
        _require(attr >> 24 == 1, "unnamed SARC member")
        name = _string(data, names + (attr & 0xffffff) * 4, payload)
        path = pathlib.PurePosixPath(name)
        _require(name not in seen and not path.is_absolute() and ".." not in path.parts,
                 "duplicate or unsafe SARC member")
        _require(0 <= start <= end <= size - payload, "invalid SARC member bounds")
        seen.add(name)
        result.append(_Member(name, payload + start, end - start))
        if end > start:
            spans.append((start, end))
    spans.sort()
    _require(all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "overlapping SARC members")
    return result


def _sections(data: bytes, magic: bytes) -> tuple[str, list[tuple[bytes, int, int]]]:
    _require(len(data) >= 20 and data[:4] == magic, "wrong layout/animation magic")
    endian = _endian(data, 4)
    header, version, size = _unpack(data, endian, "HII", 6)
    count = _unpack(data, endian, "H", 16)[0]
    _require(20 <= header <= len(data) and size == len(data), "invalid layout/animation size")
    _require(version == 0x09000000, "unsupported layout/animation version")
    sections = []
    offset = header
    for _ in range(count):
        section_size = _unpack(data, endian, "I", offset + 4)[0]
        _require(8 <= section_size <= len(data) - offset, "invalid section bounds")
        sections.append((data[offset:offset + 4], offset, offset + section_size))
        offset += section_size
    _require(offset == len(data), "trailing layout/animation sections")
    return endian, sections


def _layout(data: bytes) -> _Layout:
    endian, sections = _sections(data, b"FLYT")
    canvas_offset = None
    canvas = None
    panes: dict[str, _Pane] = {}
    stack: list[str] = []
    last = None
    for magic, start, end in sections:
        if magic == b"lyt1":
            _require(canvas_offset is None, "duplicate layout canvas")
            canvas_offset = start + 12
            canvas = _unpack(data, endian, "2f", canvas_offset, end)
        elif magic in _PANE_KINDS:
            _require(end - start >= 84, "short pane")
            name = _fixed_string(data, start + 12, start + 36)
            _require(name not in panes, "duplicate pane name")
            values = _unpack(data, endian, "10f", start + 44, end)
            _require(all(math.isfinite(v) for v in values), "nonfinite pane field")
            panes[name] = _Pane(name, stack[-1] if stack else None, magic, start,
                                data[start + 9], values[:3], values[3:6], values[6:8], values[8:10])
            last = name
        elif magic == b"pas1":
            _require(last is not None, "pane parent without pane")
            stack.append(last)
        elif magic == b"pae1":
            _require(bool(stack), "unbalanced pane hierarchy")
            stack.pop()
    _require(not stack and canvas_offset is not None and canvas is not None, "invalid layout hierarchy")
    return _Layout(endian, canvas_offset, canvas, panes)


def _stem(name: str) -> str:
    return pathlib.PurePosixPath(name).stem.split("+", 1)[0]


def _animation_owner(name: str, layouts: dict[str, _Layout]) -> str | None:
    stem = _stem(name)
    matches = [key for key in layouts if stem == _stem(key) or stem.startswith(_stem(key) + "_")]
    if not matches:
        return None
    matches.sort(key=lambda key: len(_stem(key)), reverse=True)
    _require(len(matches) == 1 or len(_stem(matches[0])) > len(_stem(matches[1])),
             "ambiguous animation owner")
    return matches[0]


def _tracks(data: bytes) -> Iterator[tuple[str, int, int, int, int, int]]:
    """Yield FLPA pane, channel, curve, key count, key data offset, section end."""
    endian, sections = _sections(data, b"FLAN")
    for magic, start, end in sections:
        if magic != b"pai1":
            continue
        count, table = _unpack(data, endian, "HI", start + 14, end)
        _unpack(data, endian, f"{count}I", start + table, end)
        for index in range(count):
            row = start + _unpack(data, endian, "I", start + table + index * 4, end)[0]
            _require(start <= row <= end - 32, "animation entry outside section")
            name = _fixed_string(data, row, row + 28)
            tags, kind = data[row + 28:row + 30]
            _unpack(data, endian, f"{tags}I", row + 32, end)
            for tag_index in range(tags):
                tag = row + _unpack(data, endian, "I", row + 32 + tag_index * 4, end)[0]
                tag += 4 if kind == 2 else 0
                _require(start <= tag <= end - 8, "animation tag outside section")
                if data[tag:tag + 4] != b"FLPA" or kind != 0:
                    continue
                tracks = data[tag + 4]
                _unpack(data, endian, f"{tracks}I", tag + 8, end)
                for track_index in range(tracks):
                    track = tag + _unpack(data, endian, "I", tag + 8 + track_index * 4, end)[0]
                    _require(start <= track <= end - 12, "animation track outside section")
                    array_index, channel, curve = data[track:track + 3]
                    _require(array_index == 0, "unknown pane animation index")
                    keys = _unpack(data, endian, "H", track + 4, end)[0]
                    key_data = track + _unpack(data, endian, "I", track + 8, end)[0]
                    _require(start <= key_data <= end, "animation keys outside section")
                    yield name, channel, curve, keys, key_data, end


def _full_screen_fill(pane: _Pane, layout: _Layout, member_name: str) -> bool:
    """Admit full-canvas background/fade/clip geometry, never text or parts."""
    if pane.kind not in (b"pic1", b"wnd1", b"bnd1", b"scr1"):
        return False
    named_fill = bool(_FILL_NAME.search(pane.name)) or pane.name in _EXTRA_FILL_NAMES
    background_layer = bool(_FILL_LAYOUT.search(_stem(member_name))) and not _CONTENT_CAPTURE.search(pane.name)
    pause_border = member_name == "blyt/info_pause_lct_edge.bflyt" and pane.name == "edge_y"
    if not (named_fill or background_layer or pause_border):
        return False
    if pane.kind in (b"bnd1", b"scr1") and "mask" not in pane.name:
        return False  # Effect emitter/hit bounds are not screen masks.
    if layout.canvas not in ((1920.0, 1080.0), (1280.0, 720.0)):
        return False
    return (pane.size[0] * abs(pane.scale[0]) >= layout.canvas[0] * 0.95
            and pane.size[1] * abs(pane.scale[1]) >= layout.canvas[1] * 0.95)


def transform_sarc(data: bytes, archive_hash40: str) -> tuple[bytes, dict]:
    """Transform one admitted original SARC and return bytes plus a JSON receipt.

    Unknown hashes, changed originals, malformed resources and unsupported key
    formats raise ResourceError before any result is returned. The input bytes
    and every directory, alignment byte, texture and shader remain untouched.
    """
    _require(isinstance(data, bytes), "resource input must be immutable bytes")
    _require(isinstance(archive_hash40, str) and archive_hash40 in _PROFILES,
             "UI archive is outside the exact 13.0.5 US-English profile")
    expected_sha, expected_size, primary_name = _PROFILES[archive_hash40]
    digest = hashlib.sha256(data).hexdigest()
    _require(len(data) == expected_size and digest == expected_sha,
             f"UI archive {archive_hash40} differs from the admitted original")
    return _transform(data, archive_hash40, primary_name)


def _transform(data: bytes, archive_hash40: str, primary_name: str) -> tuple[bytes, dict]:
    """Apply the already identity-checked resource policy; tests use synthetic bytes."""
    members = _members(data)
    by_name = {member.name: member for member in members}
    _require("info/layout.info" in by_name, "missing engine primary layout identity")
    info = by_name["info/layout.info"]
    _require(_string(data, info.offset, info.offset + info.size) == primary_name,
             "engine primary layout identity mismatch")
    primary = "blyt/" + primary_name
    _require(primary in by_name, "missing engine primary layout")
    layouts = {member.name: _layout(data[member.offset:member.offset + member.size])
               for member in members if member.name.endswith(".bflyt")}
    layout = layouts[primary]
    _require(layout.canvas in ((1920.0, 1080.0), (1280.0, 720.0)), "unsupported primary screen canvas")
    roots = [pane for pane in layout.panes.values() if pane.parent is None]
    _require(len(roots) == 1 and roots[0].name == "RootPane" and roots[0].size == layout.canvas
             and roots[0].position == (0.0, 0.0, 0.0) and roots[0].scale == (1.0, 1.0),
             "primary root differs from the admitted centered screen")
    output = bytearray(data)
    changes: list[dict] = []
    touched: set[int] = set()

    def change(member_name: str, offset: int, new_value: float, pane: str, field: str, policy: str) -> None:
        member = by_name[member_name]
        endian = layouts[member_name].endian if member_name in layouts else _endian(data[member.offset:member.offset + member.size], 4)
        old = _unpack(data, endian, "f", member.offset + offset, member.offset + member.size)[0]
        _require(math.isfinite(old) and math.isfinite(new_value), "nonfinite transformed field")
        encoded = struct.pack(endian + "f", new_value)
        absolute = member.offset + offset
        _require(absolute not in touched, "overlapping UI transformations")
        touched.add(absolute)
        if encoded != data[absolute:absolute + 4]:
            output[absolute:absolute + 4] = encoded
            changes.append({"member": member_name, "offset": offset, "pane": pane,
                            "field": field, "before": data[absolute:absolute + 4].hex(),
                            "after": encoded.hex(), "policy": policy})

    factor = 4.0 / 3.0
    change(primary, layout.canvas_offset + 4, layout.canvas[1] * factor, "", "canvas_height", "screen_canvas")
    change(primary, roots[0].offset + 80, roots[0].size[1] * factor, "RootPane", "height", "screen_root")
    # Rules are per-layout/per-pane and reused for all bound animation files.
    rules: dict[str, dict[str, dict[int, tuple[float, float, str]]]] = {
        primary: {"RootPane": {9: (factor, 0.0, "screen_root")}}
    }
    root_stem = _stem(primary)
    edges = _EDGE_GROUPS.get(root_stem, {})
    _require(all(name in layout.panes for name in edges), "missing explicit edge group")
    for name, offset_y in edges.items():
        pane = layout.panes[name]
        ancestor = pane.parent
        while ancestor is not None:
            _require(ancestor not in edges, "edge groups would move a descendant twice")
            ancestor = layout.panes[ancestor].parent
        _require(((pane.origin >> 6) & 3) == 0, "edge group already uses a parent Y origin")
        delta = offset_y * layout.canvas[1] / 1080.0
        change(primary, pane.offset + 48, pane.position[1] + delta, name, "y", "edge_anchor")
        rules.setdefault(primary, {}).setdefault(name, {})[1] = (1.0, delta, "edge_anchor")

    fills = 0
    for name, current in layouts.items():
        targets = [pane for pane in current.panes.values() if _full_screen_fill(pane, current, name)]
        for pane in targets:
            # Rotated fills grow uniformly so a quarter-turn mask still fills Y.
            channels = (8, 9) if any(pane.rotation) else (9,)
            own_rules = rules.setdefault(name, {}).setdefault(pane.name, {})
            for channel in channels:
                dimension = channel - 8
                change(name, pane.offset + 76 + dimension * 4, pane.size[dimension] * factor,
                       pane.name, "width" if dimension == 0 else "height", "full_screen_fill")
                own_rules[channel] = (factor, 0.0, "full_screen_fill")
            # Hold the geometric center fixed when an origin is not centered.
            # Geometry is scaled/rotated before pane translation. Parent-origin
            # binds also respond to a resized parent's dimensions.
            own_x, own_y = pane.origin & 3, (pane.origin >> 2) & 3
            parent_x, parent_y = (pane.origin >> 4) & 3, (pane.origin >> 6) & 3
            _require(max(own_x, own_y, parent_x, parent_y) < 3, "unknown fill origin")
            dw = pane.size[0] * (factor - 1.0) if 8 in channels else 0.0
            dh = pane.size[1] * (factor - 1.0)
            x = (0, -1, 1)[own_x] * dw * pane.scale[0] / 2.0
            y = (0, 1, -1)[own_y] * dh * pane.scale[1] / 2.0
            _require(not any(pane.rotation[:2]) or (x == 0 and y == 0),
                     "noncentered 3D fill requires a separate geometry profile")
            angle = math.radians(pane.rotation[2])
            delta_x = math.cos(angle) * x - math.sin(angle) * y
            delta_y = math.sin(angle) * x + math.cos(angle) * y
            parent = current.panes.get(pane.parent)
            if parent is not None and (parent in targets or (name == primary and parent.name == "RootPane")):
                parent_dw = parent.size[0] * (factor - 1.0) if parent in targets and any(parent.rotation) else 0.0
                delta_x -= (0, -1, 1)[parent_x] * parent_dw / 2.0
                delta_y -= (0, 1, -1)[parent_y] * parent.size[1] * (factor - 1.0) / 2.0
            for channel, delta in ((0, delta_x), (1, delta_y)):
                if delta:
                    _require(channel not in own_rules, "fill and explicit edge policies conflict")
                    change(name, pane.offset + 44 + channel * 4, pane.position[channel] + delta,
                           pane.name, "x" if channel == 0 else "y", "fill_origin")
                    own_rules[channel] = (1.0, delta, "fill_origin")
            fills += 1

    animation_files = 0
    animation_keys = 0
    for member in members:
        if not member.name.endswith(".bflan"):
            continue
        owner = _animation_owner(member.name, layouts)
        if owner not in rules:
            continue
        payload = data[member.offset:member.offset + member.size]
        endian = _endian(payload, 4)
        before_count = len(changes)
        for pane, channel, curve, count, start, end in _tracks(payload):
            rule = rules[owner].get(pane, {}).get(channel)
            if rule is None:
                continue
            # This exact build contains only FLPA Hermite tracks. Step encodings
            # of other tag types must not be treated as float translation keys.
            _require(curve == 2, "unsupported relevant FLPA curve; expected Hermite")
            _unpack(payload, endian, f"{count * 3}f", start, end)
            scale, delta, policy = rule
            for index in range(count):
                key = start + index * 12
                frame, value, slope = _unpack(payload, endian, "3f", key, end)
                _require(all(math.isfinite(v) for v in (frame, value, slope)), "nonfinite animation key")
                change(member.name, key + 4, value * scale + delta, pane,
                       f"FLPA[{channel}].value", policy)
                if scale != 1.0:
                    change(member.name, key + 8, slope * scale, pane,
                           f"FLPA[{channel}].slope", policy)
                animation_keys += 1
        animation_files += len(changes) != before_count
    result = bytes(output)
    receipt = {"schema": 1, "profile": "smash-13.0.5-us_en-4:3-ui-v1",
               "archive_hash40": archive_hash40, "original_sha256": hashlib.sha256(data).hexdigest(),
               "transformed_sha256": hashlib.sha256(result).hexdigest(), "bytes": len(data),
               "primary_layout": primary, "canvas_before": list(layout.canvas),
               "canvas_after": [layout.canvas[0], layout.canvas[1] * factor],
               "content_policy": "explicit_edge_groups_and_centered_menu_content",
               "edge_groups": len(edges), "full_screen_fills": fills,
               "animation_files": animation_files, "animation_keys": animation_keys,
               "changed_fields": len(changes), "changes": changes}
    return result, receipt
