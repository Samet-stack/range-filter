"""One active model, bounded forecast cache, and serialized model loading/inference."""
from collections import OrderedDict
import gc
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kronos_runtime import BASE_MODEL, CONTEXT, EXPERIMENT, HORIZON, KRONOS_ROOT, TOKENIZER, gpu_slot

MODELS = {
    "original": dict(label="Kronos original", path=BASE_MODEL, volume=False,
                     note="Tests 2026 en 1h/4h : aucun avantage directionnel démontré."),
    "crypto-v1": dict(label="Crypto V1 · réentraîné", path=str(KRONOS_ROOT / "finetuned/crypto/best"), volume=False,
                      note="Adapté à BTC, ETH, HYPE et ZEC. Les tests 2026 restent derrière la méthode simple."),
    "crypto-v2": dict(label="Crypto V2 · prix + volumes", path=str(EXPERIMENT / "best"), volume=True,
                      note="Expérience sur Binance/Bybit. Son efficacité sur Hyperliquid reste à mesurer."),
}


def available(model):
    if model == "crypto-v2":
        report_path = EXPERIMENT / "report.json"
        if not report_path.exists() or json.loads(report_path.read_text()).get("status") != "complete":
            return False
    return model == "original" or (Path(MODELS[model]["path"]) / "model.safetensors").is_file()


def catalog():
    report = None
    report_path = EXPERIMENT / "report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text())
    return dict(horizon=HORIZON, models=[dict(id=k, label=v["label"], note=v["note"], available=available(k))
                                      for k, v in MODELS.items()], experiment=report)


class KronosService:
    def __init__(self, loader=None, infer=None, capacity=64):
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.capacity = capacity
        self.predictor = None
        self.active = None
        self.loader = loader or self._load
        self.infer = infer or self._infer

    def _load(self, model):
        sys.path.insert(0, str(KRONOS_ROOT))
        import torch
        from model import Kronos, KronosPredictor, KronosTokenizer
        self.predictor = None
        self.active = None
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return KronosPredictor(Kronos.from_pretrained(MODELS[model]["path"]).eval(),
                               KronosTokenizer.from_pretrained(TOKENIZER).eval(),
                               device="cuda:0" if torch.cuda.is_available() else "cpu", max_context=512)

    def _infer(self, predictor, rows, times, model, seed):
        import numpy as np
        import pandas as pd
        import torch
        cols = ["open", "high", "low", "close"] + (["volume", "amount"] if MODELS[model]["volume"] else [])
        df = pd.DataFrame([r[1:1 + len(cols)] for r in rows], columns=cols)
        xts = pd.Series(pd.to_datetime([r[0] for r in rows], unit="ms"))
        yts = pd.Series(pd.to_datetime(times, unit="ms"))
        paths = []
        devices = [torch.cuda.current_device()] if str(predictor.device).startswith("cuda") else []
        with torch.random.fork_rng(devices=devices), torch.inference_mode():
            torch.manual_seed(seed)
            # Keep peak memory bounded instead of putting all 50 paths on the GPU at once.
            for _ in range(5):
                ps = predictor.predict_batch([df] * 10, [xts] * 10, [yts] * 10, pred_len=HORIZON,
                                             T=1.0, top_p=0.9, sample_count=1, verbose=False)
                paths.extend(p["close"].tolist() for p in ps)
        values = np.asarray(paths)
        if values.shape != (50, HORIZON) or not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Kronos a renvoyé une prévision invalide.")
        return paths

    def forecast(self, sym, tf, source, rows, step, model="original"):
        if model not in MODELS:
            raise ValueError("Modèle Kronos inconnu.")
        if not available(model):
            raise LookupError("Ce modèle n'est pas encore disponible.")
        rows = rows[-CONTEXT:]
        if len(rows) < CONTEXT:
            raise ValueError(f"Kronos nécessite {CONTEXT} bougies clôturées.")
        if any(b[0] - a[0] != step for a, b in zip(rows, rows[1:])):
            raise ValueError("L'historique contient des bougies manquantes ; prévision suspendue.")
        if MODELS[model]["volume"] and any(len(r) < 7 for r in rows):
            raise ValueError("Les volumes sont nécessaires pour ce modèle.")
        weights = Path(MODELS[model]["path"]) / "model.safetensors"
        revision = weights.stat().st_mtime_ns if weights.is_file() else 0
        fingerprint = hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]
        key = (sym, tf, source, model, revision, fingerprint)
        # Serializes cache lookup, model initialization AND inference, including duplicate requests.
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            with gpu_slot():
                if self.active != (model, revision):
                    self.predictor = self.loader(model)
                    self.active = (model, revision)
                times = [rows[-1][0] + step * i for i in range(1, HORIZON + 1)]
                seed = int(hashlib.sha256(repr(key).encode()).hexdigest()[:8], 16)
                paths = self.infer(self.predictor, rows, times, model, seed)
            result = dict(sym=sym, tf=tf, src=source, model=model, model_label=MODELS[model]["label"],
                          horizon=HORIZON, context=CONTEXT, generated_at=int(time.time()),
                          start=dict(time=rows[-1][0] // 1000, value=rows[-1][4]),
                          times=[t // 1000 for t in times], paths=paths)
            self.cache[key] = result
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            return result
