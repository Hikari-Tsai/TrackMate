import numpy as np
import pytest
import soundfile as sf

from cases import SR, build_cases
from stereo_analyzer import Action, StereoType, analyze, write_downmix

CASES = build_cases()


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    root = tmp_path_factory.mktemp("stems")
    paths = {}
    for i, (name, data, _) in enumerate(CASES):
        path = root / f"case{i:02d}.wav"
        sf.write(path, data, SR, subtype="PCM_24")
        paths[name] = str(path)
    return paths


@pytest.mark.parametrize("name,data,expected", CASES, ids=[c[0] for c in CASES])
def test_classification(files, name, data, expected):
    assert analyze(files[name]).stereo_type.value == expected


@pytest.mark.parametrize("name,data,expected", [c for c in CASES if c[2] in ("fake_stereo", "hard_left", "hard_right")],
                         ids=[c[0] for c in CASES if c[2] in ("fake_stereo", "hard_left", "hard_right")])
def test_downmix_keeps_level_and_never_cancels(files, tmp_path, name, data, expected):
    a = analyze(files[name])
    out, _ = sf.read(write_downmix(a, str(tmp_path / "out.wav")))
    louder = data[:, int(np.argmax(np.sqrt((data ** 2).mean(0))))]
    rms = lambda x: float(np.sqrt(np.mean(x ** 2)))
    # same level as the louder channel (within 0.5 dB) and the same waveform
    assert abs(20 * np.log10(rms(out) / rms(louder))) < 0.5
    assert np.corrcoef(out, louder)[0, 1] > 0.99


def test_pan_and_polarity_reported(files):
    left = analyze(files["mono panned 30% left"])
    assert left.pan == pytest.approx(-0.3, abs=0.02)
    inverted = analyze(files["polarity inverted (R = -L)"])
    assert inverted.polarity_inverted and inverted.action is Action.DOWNMIX


def test_haas_delay_measured(files):
    a = analyze(files["Haas: right delayed 12 ms"])
    assert a.delay_ms == pytest.approx(12.0, abs=0.1)
    assert a.action is Action.KEEP


def test_mono_and_silent_files(tmp_path):
    mono = tmp_path / "mono.wav"
    sf.write(mono, np.zeros(SR) + 0.1, SR)
    assert analyze(str(mono)).stereo_type is StereoType.MONO_FILE
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros((SR, 2)), SR)
    assert analyze(str(silent)).stereo_type is StereoType.SILENT
