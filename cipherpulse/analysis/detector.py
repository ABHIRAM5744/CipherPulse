"""Real-time anomaly detection.

Layers: hard limits (phase-aware) + rolling z-score + Isolation Forest + cross-signal correlator
+ short-horizon trend forecast (early warning) + a 0-100 health index per astronaut.
"""
from collections import deque
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import IsolationForest

KEYS = ["hr", "spo2", "temp", "resp", "radiation"]
DEFAULT_LIMITS = {  # (warn_low, warn_high, crit_low, crit_high)
    "hr": (50, 105, 40, 140),
    "spo2": (94, 101, 90, 101),
    "temp": (35.8, 37.9, 35.0, 39.0),
    "resp": (9, 22, 6, 30),
    "radiation": (-1, 3.0, -1, 8.0),
}
LIMITS = {k: tuple(v) for k, v in DEFAULT_LIMITS.items()}  # editable at runtime
LABEL = {"hr": "Heart rate", "spo2": "Blood oxygen", "temp": "Temperature", "resp": "Breathing rate", "radiation": "Radiation"}
UNIT = {"hr": "bpm", "spo2": "%", "temp": "C", "resp": "/min", "radiation": "uSv/h"}

# mission phases relax the *warning* limits (critical limits never move)
PHASES = {
    "orbit": {},
    "launch": {"hr": (None, 135), "resp": (None, 30)},
    "eva": {"hr": (None, 135), "resp": (None, 30), "temp": (None, 38.3)},
    "sleep": {"hr": (38, None), "resp": (6, None)},
}
TREND = {"spo2": -1, "hr": +1, "temp": +1, "radiation": +1}          # direction toward the warning limit
MIN_SLOPE = {"spo2": 0.04, "hr": 0.45, "temp": 0.008, "radiation": 0.05}  # units per second
FORECAST_HORIZON_S = 45
MIN_SD = {"hr": 1.5, "spo2": 0.35, "temp": 0.06, "resp": 0.8, "radiation": 0.05}  # floors so a flat baseline cannot cause false alarms
Z_LIMIT = 6.0


def set_limits(new: dict):
    """Validate and apply new limits. Returns the active limits."""
    for k, v in new.items():
        if k in KEYS and len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
            wl, wh, cl, ch = v
            if wl <= wh and cl <= wl + 1e-9 + (0 if wl > -1 else 1) and ch >= wh - 1e-9:
                LIMITS[k] = (float(wl), float(wh), float(cl), float(ch))
    return LIMITS


def reset_limits():
    LIMITS.update({k: tuple(v) for k, v in DEFAULT_LIMITS.items()})
    return LIMITS


@dataclass
class Finding:
    severity: str = "ok"          # ok | warning | critical
    kind: str = "normal"
    reasons: list = field(default_factory=list)
    ml_score: float = 0.0
    index: int = 100              # 0-100 health index
    eta: float | None = None      # seconds until a limit is crossed (forecast)


def _train_forest():
    rng = np.random.default_rng(7)
    n = 3000
    X = np.column_stack([
        rng.normal(66, 6, n), rng.normal(97.8, 0.7, n), rng.normal(36.65, 0.15, n),
        rng.normal(14.5, 1.6, n), np.abs(rng.normal(0.38, 0.1, n)),
    ])
    return IsolationForest(n_estimators=120, contamination=0.005, random_state=7).fit(X)


class Detector:
    def __init__(self):
        self.forest = _train_forest()
        self.hist = {}      # astro -> deque of NORMAL vectors (baseline learning)
        self.recent = {}    # astro -> deque of ALL vectors (trend fitting)
        self.ml_streak = {}
        self.index = {}

    @staticmethod
    def limits(k, phase="orbit"):
        wl, wh, cl, ch = LIMITS[k]
        adj = PHASES.get(phase, {}).get(k)
        if adj:
            if adj[0] is not None:
                wl = adj[0]
            if adj[1] is not None:
                wh = adj[1]
        return wl, wh, cl, ch

    def _health_index(self, astro, v, score, phase):
        pen = 0.0
        for k in KEYS:
            wl, wh, _, _ = self.limits(k, phase)
            x = v[k]
            width = max(1e-6, (wh - wl) if wl > -1 else wh)
            dev = max(((wl - x) / width) if wl > -1 else 0.0, (x - wh) / width, 0.0)
            pen += min(30.0, dev * 45.0)
        pen += min(15.0, max(0.0, -score) * 60.0)
        raw = max(0.0, 100.0 - pen)
        cur = self.index.get(astro, 100.0)
        cur += (raw - cur) * 0.3
        self.index[astro] = cur
        return int(round(cur))

    def _forecast(self, astro, v, phase):
        r = self.recent.get(astro)
        if not r or len(r) < 25:
            return None
        arr = np.array(list(r)[-25:])
        t = np.arange(25, dtype=float)
        best = None
        for i, k in enumerate(KEYS):
            if k not in TREND:
                continue
            y = arr[:, i]
            if np.ptp(y) < 1e-9:
                continue
            slope, icpt = np.polyfit(t, y, 1)
            fit = slope * t + icpt
            r2 = 1 - ((y - fit) ** 2).sum() / (((y - y.mean()) ** 2).sum() + 1e-9)
            if r2 < 0.6:
                continue
            wl, wh, _, _ = self.limits(k, phase)
            cur = v[k]
            if TREND[k] < 0 and slope < -MIN_SLOPE[k] and cur > wl:
                eta = (cur - wl) / -slope
            elif TREND[k] > 0 and slope > MIN_SLOPE[k] and cur < wh:
                eta = (wh - cur) / slope
            else:
                continue
            if 0 < eta <= FORECAST_HORIZON_S and (best is None or eta < best[1]):
                best = (k, float(eta), float(slope))
        return best

    def update(self, astro, v: dict, phase: str = "orbit") -> Finding:
        vec = np.array([v[k] for k in KEYS], dtype=float)
        h = self.hist.setdefault(astro, deque(maxlen=150))
        rec = self.recent.setdefault(astro, deque(maxlen=60))
        rec.append(vec)
        f = Finding()
        flags = {}

        for k in KEYS:  # 1) hard limits
            wl, wh, cl, ch = self.limits(k, phase)
            x = v[k]
            if x <= cl or x >= ch:
                flags[k] = "critical"
            elif x <= wl or x >= wh:
                flags[k] = "warning"

        if len(h) >= 40:  # 2) rolling baseline z-score
            arr = np.array(h)
            mu = arr.mean(0)
            sd = np.maximum(arr.std(0), np.array([MIN_SD[k] for k in KEYS]))
            z = (vec - mu) / sd
            for i, k in enumerate(KEYS):
                if abs(z[i]) > Z_LIMIT and k not in flags:
                    flags[k] = "warning"

        # 3) Isolation Forest, 3 consecutive anomalous samples to avoid blips
        score = float(self.forest.decision_function(vec.reshape(1, -1))[0])
        f.ml_score = round(score, 3)
        anomalous = self.forest.predict(vec.reshape(1, -1))[0] == -1
        self.ml_streak[astro] = self.ml_streak.get(astro, 0) + 1 if anomalous else 0
        ml_flag = self.ml_streak[astro] >= 3 and phase == "orbit"

        # 4) cross-signal correlator (pattern naming)
        hr_up, resp_up, spo2_down = v["hr"] > 95, v["resp"] > 19, v["spo2"] < 95
        if v["hr"] > 84 and resp_up and spo2_down:
            f.kind = "air_quality"
        elif v["temp"] >= 37.9 and hr_up:
            f.kind = "fever_pattern"
        elif v["radiation"] >= 3.0:
            f.kind = "radiation_event"
        elif hr_up and resp_up:
            f.kind = "exertion"
        elif "spo2" in flags:
            f.kind = "low_oxygen"
        elif flags:
            f.kind = f"{next(iter(flags))}_out_of_range"
        elif ml_flag:
            f.kind = "ml_anomaly"
            flags["ml"] = "warning"

        if flags:
            f.severity = "critical" if "critical" in flags.values() else "warning"
            f.reasons = [
                (f"{LABEL[k]} {v[k]} {UNIT[k]} is outside the safe range" if k in v else "Unusual combination of vitals (ML model)")
                for k in flags
            ]
        else:
            h.append(vec)  # learn the baseline only from normal data
            # 5) early warning: nothing flagged yet, but a clear trend will cross a limit soon
            fc = self._forecast(astro, v, phase)
            if fc:
                k, eta, slope = fc
                f.severity, f.kind, f.eta = "warning", f"trend_{k}", round(eta)
                f.reasons = [f"{LABEL[k]} is {'falling' if slope < 0 else 'rising'} {abs(slope):.2f} {UNIT[k]} per second and is projected to cross its warning limit in about {round(eta)} s"]

        f.index = self._health_index(astro, v, score, phase)
        return f
