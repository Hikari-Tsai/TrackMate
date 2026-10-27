"""Build the text prototypes for the PE-AV instrument demo Space (PyTorch, offline).

The Space runs only the ONNX audio encoder, so every label's text embedding is computed here
once with PE-AV's own text encoder: mean of its prompts x templates, the same recipe as
engine/tools/build_peav_prototypes.py. Prompts are English (the tokenizer is English-only).

Output (in tools/peav_space/space/):
  prototypes.npz  keys, en, zh, family [n] + prototypes [n, 1024] float32, not normalised
  labels.json     the same labels with their prompts, for anyone reading the Space

Run from the repo root (needs the PyTorch model; transformers 5.20.2):
  uv run --no-project --python 3.12 --with numpy --with soundfile --with soxr --with librosa \
    --with "transformers==5.20.2" --with torch --with timm --with pillow \
    python tools/peav_space/build_prototypes.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "instrument_zeroshot"))
from eval_instruments import PEAV  # noqa: E402

OUT = HERE / "space"
TEMPLATES = ["the sound of {}", "a recording of {}", "{}", "solo {}"]

FAMILIES = {
    "keys": "鍵盤", "free_reed": "簧片樂器", "guitar": "吉他", "bass": "貝斯", "bowed": "弓弦樂器",
    "plucked": "撥弦樂器", "brass": "銅管", "woodwind": "木管", "drums": "鼓組", "percussion": "打擊樂器",
    "mallet": "有音高敲擊", "electronic": "電子／合成器", "fx": "音效", "vocals": "人聲",
    "east_asian": "東亞傳統樂器", "world": "世界音樂", "ensemble": "合奏", "other": "非樂器",
}

# family -> [(key, English name, 中文名稱, prompts)]
LABELS: dict[str, list[tuple[str, str, str, list[str]]]] = {
    "keys": [
        ("grand_piano", "Grand piano", "平台鋼琴", ["a grand piano", "an acoustic piano"]),
        ("upright_piano", "Upright piano", "直立式鋼琴", ["an upright piano", "an old honky-tonk upright piano"]),
        ("electric_piano", "Electric piano (Rhodes)", "電鋼琴（Rhodes）", ["a Rhodes electric piano", "an electric piano"]),
        ("wurlitzer", "Wurlitzer", "Wurlitzer 電鋼琴", ["a Wurlitzer electric piano"]),
        ("hammond_organ", "Hammond organ", "哈蒙德風琴", ["a Hammond organ", "a rock organ with a rotary speaker"]),
        ("pipe_organ", "Pipe organ", "管風琴", ["a church pipe organ", "a pipe organ"]),
        ("harpsichord", "Harpsichord", "大鍵琴", ["a harpsichord", "a baroque harpsichord"]),
        ("clavinet", "Clavinet", "克拉維內特琴", ["a funky clavinet", "a clavinet"]),
        ("celesta", "Celesta", "鋼片琴", ["a celesta"]),
    ],
    "free_reed": [
        ("accordion", "Accordion", "手風琴", ["an accordion"]),
        ("bandoneon", "Bandoneon", "班多鈕手風琴", ["a bandoneon playing tango"]),
        ("harmonica", "Harmonica", "口琴", ["a harmonica", "a blues harmonica"]),
        ("melodica", "Melodica", "口風琴", ["a melodica"]),
        ("harmonium", "Harmonium", "簧風琴", ["a harmonium", "an Indian harmonium"]),
    ],
    "guitar": [
        ("acoustic_guitar", "Acoustic guitar (steel string)", "木吉他（鋼弦）",
         ["a steel-string acoustic guitar", "an acoustic guitar strumming chords"]),
        ("classical_guitar", "Classical guitar", "古典吉他", ["a nylon-string classical guitar", "a classical guitar"]),
        ("twelve_string_guitar", "12-string guitar", "十二弦吉他", ["a twelve-string acoustic guitar"]),
        ("clean_electric_guitar", "Electric guitar (clean)", "電吉他（乾淨音色）",
         ["a clean electric guitar", "a clean electric guitar playing chords"]),
        ("distorted_guitar", "Electric guitar (distorted)", "破音電吉他",
         ["a distorted electric guitar", "a heavy metal guitar riff"]),
        ("jazz_guitar", "Jazz guitar", "爵士吉他", ["a hollow-body jazz guitar"]),
        ("slide_guitar", "Slide guitar", "滑音吉他", ["a slide guitar", "a bottleneck slide guitar"]),
        ("pedal_steel", "Pedal steel guitar", "踏板滑音吉他", ["a pedal steel guitar"]),
    ],
    "bass": [
        ("electric_bass", "Electric bass", "電貝斯", ["an electric bass guitar", "a fingerstyle electric bass line"]),
        ("slap_bass", "Slap bass", "擊勾貝斯", ["a slap bass"]),
        ("fretless_bass", "Fretless bass", "無琴格貝斯", ["a fretless bass"]),
        ("upright_bass", "Upright bass (pizzicato)", "低音提琴（撥奏）",
         ["an upright double bass played pizzicato", "a jazz upright bass"]),
        ("synth_bass", "Synth bass", "合成器貝斯", ["a synth bass", "an analog synthesizer bass line"]),
        ("sub_808", "808 sub bass", "808 低音", ["an 808 sub bass", "a deep 808 bass"]),
    ],
    "bowed": [
        ("violin", "Violin", "小提琴", ["a violin"]),
        ("viola", "Viola", "中提琴", ["a viola"]),
        ("cello", "Cello", "大提琴", ["a cello"]),
        ("double_bass_arco", "Double bass (bowed)", "低音提琴（拉奏）", ["a double bass played with a bow"]),
        ("string_section", "String section", "弦樂組", ["an orchestral string section", "a string ensemble"]),
        ("pizzicato_strings", "Pizzicato strings", "撥奏弦樂", ["pizzicato strings"]),
        ("fiddle", "Fiddle", "民謠小提琴", ["a folk fiddle", "a bluegrass fiddle"]),
    ],
    "plucked": [
        ("harp", "Harp", "豎琴", ["a harp", "a concert harp"]),
        ("banjo", "Banjo", "斑鳩琴", ["a banjo"]),
        ("mandolin", "Mandolin", "曼陀林", ["a mandolin"]),
        ("ukulele", "Ukulele", "烏克麗麗", ["a ukulele"]),
        ("lute", "Lute", "魯特琴", ["a renaissance lute"]),
    ],
    "brass": [
        ("trumpet", "Trumpet", "小號", ["a trumpet"]),
        ("muted_trumpet", "Muted trumpet", "弱音小號", ["a muted trumpet"]),
        ("flugelhorn", "Flugelhorn", "富魯格號", ["a flugelhorn"]),
        ("trombone", "Trombone", "長號", ["a trombone"]),
        ("french_horn", "French horn", "法國號", ["a french horn"]),
        ("tuba", "Tuba", "低音號", ["a tuba"]),
        ("euphonium", "Euphonium", "上低音號", ["a euphonium"]),
        ("brass_section", "Brass section", "銅管組", ["a brass section", "horn section stabs"]),
    ],
    "woodwind": [
        ("flute", "Flute", "長笛", ["a flute", "a concert flute"]),
        ("piccolo", "Piccolo", "短笛", ["a piccolo"]),
        ("clarinet", "Clarinet", "單簧管", ["a clarinet"]),
        ("bass_clarinet", "Bass clarinet", "低音單簧管", ["a bass clarinet"]),
        ("oboe", "Oboe", "雙簧管", ["an oboe"]),
        ("bassoon", "Bassoon", "低音管", ["a bassoon"]),
        ("soprano_sax", "Soprano saxophone", "高音薩克斯風", ["a soprano saxophone"]),
        ("alto_sax", "Alto saxophone", "中音薩克斯風", ["an alto saxophone"]),
        ("tenor_sax", "Tenor saxophone", "次中音薩克斯風", ["a tenor saxophone"]),
        ("baritone_sax", "Baritone saxophone", "上低音薩克斯風", ["a baritone saxophone"]),
        ("recorder", "Recorder", "直笛", ["a recorder", "a recorder flute"]),
        ("pan_flute", "Pan flute", "排笛", ["a pan flute"]),
        ("tin_whistle", "Tin whistle", "錫口笛", ["an Irish tin whistle"]),
    ],
    "drums": [
        ("drum_kit", "Drum kit", "爵士鼓（套鼓）", ["a full drum kit", "a rock drum beat"]),
        ("brushed_drums", "Jazz drums (brushes)", "爵士鼓（鼓刷）", ["jazz drums played with brushes"]),
        ("kick_drum", "Kick drum", "大鼓（Kick）", ["a kick drum", "a bass drum"]),
        ("snare_drum", "Snare drum", "小鼓", ["a snare drum"]),
        ("toms", "Toms", "通鼓", ["tom-tom drums", "a drum fill on the toms"]),
        ("hi_hat", "Hi-hat", "腳踏鈸", ["a hi-hat"]),
        ("cymbals", "Cymbals", "銅鈸", ["crash cymbals", "a ride cymbal"]),
        ("drum_machine", "Drum machine", "鼓機", ["a drum machine beat", "an 808 drum machine"]),
        ("breakbeat", "Breakbeat", "碎拍（Breakbeat）", ["a breakbeat", "a sampled funk breakbeat"]),
    ],
    "percussion": [
        ("congas", "Congas", "康加鼓", ["congas"]),
        ("bongos", "Bongos", "邦哥鼓", ["bongos"]),
        ("cajon", "Cajón", "木箱鼓", ["a cajon"]),
        ("tambourine", "Tambourine", "鈴鼓", ["a tambourine"]),
        ("shaker", "Shaker", "沙鈴", ["a shaker", "maracas"]),
        ("cowbell", "Cowbell", "牛鈴", ["a cowbell"]),
        ("claves", "Claves", "響棒", ["claves"]),
        ("triangle", "Triangle", "三角鐵", ["a triangle"]),
        ("castanets", "Castanets", "響板", ["castanets"]),
        ("guiro", "Güiro", "刮瓜", ["a guiro"]),
        ("wood_block", "Wood block", "木魚／木塊", ["a wood block"]),
        ("timpani", "Timpani", "定音鼓", ["timpani", "orchestral kettle drums"]),
        ("gong", "Gong", "鑼", ["a gong", "a tam-tam"]),
        ("hand_claps", "Hand claps", "拍手", ["hand claps"]),
        ("finger_snaps", "Finger snaps", "彈指", ["finger snaps"]),
    ],
    "mallet": [
        ("glockenspiel", "Glockenspiel", "鐵琴", ["a glockenspiel"]),
        ("xylophone", "Xylophone", "木琴", ["a xylophone"]),
        ("marimba", "Marimba", "馬林巴", ["a marimba"]),
        ("vibraphone", "Vibraphone", "顫音琴", ["a vibraphone"]),
        ("tubular_bells", "Tubular bells", "管鐘", ["tubular bells", "orchestral chimes"]),
        ("music_box", "Music box", "音樂盒", ["a music box"]),
        ("kalimba", "Kalimba", "拇指琴", ["a kalimba", "an mbira thumb piano"]),
        ("steel_pan", "Steel pan", "鋼鼓", ["a steel pan", "a Caribbean steel drum"]),
        ("handbells", "Handbells", "手搖鈴", ["handbells"]),
        ("handpan", "Handpan", "手碟", ["a handpan", "a hang drum"]),
    ],
    "electronic": [
        ("synth_lead", "Synth lead", "合成器主音", ["a synth lead", "a lead synthesizer melody"]),
        ("synth_pad", "Synth pad", "合成器鋪底", ["a synth pad", "a lush ambient synthesizer pad"]),
        ("synth_arp", "Arpeggiated synth", "琶音合成器", ["an arpeggiated synthesizer"]),
        ("supersaw", "Supersaw synth", "超級鋸齒波合成器", ["a supersaw trance synth", "an EDM supersaw lead"]),
        ("chiptune", "Chiptune (8-bit)", "晶片音樂（8-bit）", ["8-bit chiptune video game music"]),
        ("theremin", "Theremin", "特雷門琴", ["a theremin"]),
        ("vocoder", "Vocoder", "聲碼器", ["a vocoder voice"]),
        ("turntable_scratch", "Turntable scratching", "DJ 刷碟", ["DJ turntable scratching"]),
    ],
    "fx": [
        ("riser", "Riser", "上升音效（Riser）", ["a riser sound effect", "a build-up white noise riser"]),
        ("impact", "Impact", "撞擊音效", ["a cinematic impact sound effect", "a boom hit"]),
        ("whoosh", "Whoosh", "呼嘯音效", ["a whoosh sound effect"]),
        ("reverse_cymbal", "Reverse cymbal", "反轉鈸", ["a reversed cymbal swell"]),
    ],
    "vocals": [
        ("male_singer", "Male singer", "男聲演唱", ["a male singer", "a man singing"]),
        ("female_singer", "Female singer", "女聲演唱", ["a female singer", "a woman singing"]),
        ("child_singer", "Child singer", "童聲", ["a child singing"]),
        ("choir", "Choir", "合唱團", ["a choir", "a church choir"]),
        ("backing_vocals", "Backing vocals", "和聲", ["backing vocals", "background singers harmonizing"]),
        ("opera_singer", "Opera singer", "歌劇美聲", ["an opera singer", "an operatic soprano"]),
        ("falsetto", "Falsetto", "假音", ["a falsetto voice"]),
        ("rap", "Rap vocal", "饒舌", ["a rapper", "rap vocals"]),
        ("growl_vocals", "Metal growl / scream", "金屬嘶吼", ["death metal growling vocals", "screamed vocals"]),
        ("autotune_vocal", "Auto-tuned vocal", "自動修音人聲", ["an auto-tuned vocal"]),
        ("beatbox", "Beatbox", "Beatbox 口技", ["beatboxing"]),
        ("humming", "Humming", "哼唱", ["a person humming"]),
        ("whistling", "Whistling", "口哨", ["a person whistling a melody"]),
    ],
    "east_asian": [
        ("erhu", "Erhu", "二胡", ["an erhu", "a Chinese two-string fiddle"]),
        ("morin_khuur", "Morin khuur", "馬頭琴", ["a morin khuur", "a Mongolian horsehead fiddle"]),
        ("pipa", "Pipa", "琵琶", ["a pipa", "a Chinese lute"]),
        ("ruan", "Ruan", "阮", ["a ruan", "a Chinese moon guitar"]),
        ("guzheng", "Guzheng", "古箏", ["a guzheng", "a Chinese zither"]),
        ("guqin", "Guqin", "古琴", ["a guqin", "a Chinese seven-string zither"]),
        ("yangqin", "Yangqin", "揚琴", ["a yangqin", "a Chinese hammered dulcimer"]),
        ("dizi", "Dizi", "笛子", ["a dizi", "a Chinese bamboo flute"]),
        ("xiao", "Xiao", "簫", ["a xiao", "a Chinese vertical bamboo flute"]),
        ("hulusi", "Hulusi", "葫蘆絲", ["a hulusi", "a Chinese gourd flute"]),
        ("suona", "Suona", "嗩吶", ["a suona", "a Chinese double-reed horn"]),
        ("sheng", "Sheng", "笙", ["a sheng", "a Chinese mouth organ"]),
        ("chinese_percussion", "Chinese opera percussion", "鑼鼓（戲曲打擊）",
         ["Chinese opera percussion with gongs and cymbals", "Chinese drums and gongs"]),
        ("koto", "Koto", "日本箏", ["a koto", "a Japanese zither"]),
        ("shamisen", "Shamisen", "三味線", ["a shamisen"]),
        ("shakuhachi", "Shakuhachi", "尺八", ["a shakuhachi", "a Japanese bamboo flute"]),
        ("taiko", "Taiko", "太鼓", ["taiko drums", "Japanese taiko drumming"]),
        ("gayageum", "Gayageum", "伽倻琴", ["a gayageum", "a Korean zither"]),
    ],
    "world": [
        ("sitar", "Sitar", "西塔琴", ["a sitar"]),
        ("tanpura", "Tanpura", "坦布拉（持續音）", ["a tanpura drone"]),
        ("tabla", "Tabla", "塔布拉鼓", ["tabla drums"]),
        ("bansuri", "Bansuri", "班蘇里笛", ["a bansuri", "an Indian bamboo flute"]),
        ("santoor", "Santoor", "桑圖爾琴", ["a santoor"]),
        ("oud", "Oud", "烏德琴", ["an oud"]),
        ("bouzouki", "Bouzouki", "布祖基琴", ["a bouzouki"]),
        ("balalaika", "Balalaika", "巴拉萊卡琴", ["a balalaika"]),
        ("ney", "Ney", "奈伊笛", ["a ney flute"]),
        ("darbuka", "Darbuka", "達布卡鼓", ["a darbuka", "a goblet drum"]),
        ("djembe", "Djembe", "金貝鼓", ["a djembe"]),
        ("talking_drum", "Talking drum", "說話鼓", ["a West African talking drum"]),
        ("kora", "Kora", "科拉琴", ["a kora", "a West African harp"]),
        ("gamelan", "Gamelan", "甘美朗", ["a gamelan ensemble"]),
        ("didgeridoo", "Didgeridoo", "迪吉里杜管", ["a didgeridoo"]),
        ("bagpipes", "Bagpipes", "風笛", ["bagpipes", "Scottish bagpipes"]),
        ("hurdy_gurdy", "Hurdy-gurdy", "手搖弦琴", ["a hurdy-gurdy"]),
        ("jaw_harp", "Jaw harp", "口簧琴", ["a jaw harp"]),
    ],
    "ensemble": [
        ("orchestra", "Full orchestra", "管弦樂團（全奏）", ["a full symphony orchestra"]),
        ("big_band", "Big band", "爵士大樂隊", ["a jazz big band"]),
        ("rock_band", "Rock band", "搖滾樂團", ["a rock band playing a song"]),
        ("full_mix", "Full song mix", "完整混音（整首歌）", ["a full song mix with many instruments",
                                                          "a pop song with vocals, drums and bass"]),
        ("string_quartet", "String quartet", "弦樂四重奏", ["a string quartet"]),
    ],
    "other": [
        ("speech", "Speech", "說話聲", ["a person talking", "people speaking"]),
        ("applause", "Applause / crowd", "掌聲／觀眾", ["applause", "a crowd cheering"]),
        ("metronome", "Metronome / click", "節拍器", ["a metronome click track", "a metronome ticking"]),
        ("noise_hum", "Hiss / hum", "底噪／嗡聲", ["background hiss and hum", "electrical noise"]),
        ("white_noise", "White noise", "白噪音", ["white noise"]),
        ("sine_tone", "Test tone", "測試音（正弦波）", ["a sine wave test tone"]),
        ("vinyl_crackle", "Vinyl crackle", "黑膠雜音", ["vinyl record crackle"]),
        ("ambience", "Room / nature ambience", "環境音", ["ambient room tone", "nature sounds such as birds and rain"]),
    ],
}


def main() -> int:
    model = PEAV()
    rows, protos = [], []
    for family, labels in LABELS.items():
        for key, en, zh, prompts in labels:
            texts = [t.format(p) for p in prompts for t in TEMPLATES]
            protos.append(model.text(texts).mean(axis=0))
            rows.append(dict(key=key, en=en, zh=zh, family=family, family_zh=FAMILIES[family], prompts=prompts))
    keys = [r["key"] for r in rows]
    if len(set(keys)) != len(keys):
        raise RuntimeError("duplicate label keys")
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez(OUT / "prototypes.npz", keys=np.array(keys), en=np.array([r["en"] for r in rows]),
             zh=np.array([r["zh"] for r in rows]), family=np.array([r["family"] for r in rows]),
             prototypes=np.stack(protos).astype(np.float32))
    (OUT / "labels.json").write_text(json.dumps(dict(templates=TEMPLATES, families=FAMILIES, labels=rows),
                                                ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {len(rows)} labels in {len(LABELS)} families to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
