from pathlib import Path
import numpy as np
import soundfile as sf

SR = 44100
ROOT = Path("samples")
for d in ["kick", "snare", "hat", "open_hat", "clap", "perc"]:
    (ROOT / d).mkdir(parents=True, exist_ok=True)

def write(path, x):
    x = x / max(1e-9, np.max(np.abs(x)))
    sf.write(path, x.astype(np.float32), SR)

t = np.arange(int(SR * .25)) / SR
kick = np.sin(2*np.pi*(80-55*t/.25)*t) * np.exp(-18*t)
write(ROOT/"kick"/"kick_demo.wav", kick)

t = np.arange(int(SR * .18)) / SR
noise = np.random.default_rng(1).normal(0, 1, len(t))
snare = noise*np.exp(-24*t) + .25*np.sin(2*np.pi*180*t)*np.exp(-30*t)
write(ROOT/"snare"/"snare_demo.wav", snare)

t = np.arange(int(SR * .08)) / SR
hat = np.random.default_rng(2).normal(0, 1, len(t))*np.exp(-70*t)
write(ROOT/"hat"/"hat_demo.wav", hat)

print("Created a tiny synthetic demo sample pack in ./samples")
