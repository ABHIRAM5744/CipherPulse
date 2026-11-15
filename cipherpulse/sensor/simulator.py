"""Physiological model for one simulated wearable."""
import math
import random
import time

PROFILES = {
    "A1": dict(hr=64, spo2=98.0, temp=36.6, resp=14, rad=0.35),
    "A2": dict(hr=68, spo2=97.5, temp=36.7, resp=15, rad=0.40),
    "A3": dict(hr=60, spo2=98.5, temp=36.5, resp=13, rad=0.30),
    "A4": dict(hr=72, spo2=97.0, temp=36.8, resp=16, rad=0.45),
}

# scenario -> (target deltas, duration seconds)
SCENARIOS = {
    "exercise":  (dict(hr=+55, resp=+10, temp=+0.7, spo2=-0.5), 40),
    "co2":       (dict(hr=+28, resp=+9, spo2=-7.5, temp=+0.1), 45),
    "radiation": (dict(rad=+9.0, hr=+6), 35),
    "fever":     (dict(temp=+2.0, hr=+22, resp=+4), 50),
    "sleep":     (dict(hr=-10, resp=-3, temp=-0.3), 40),
}


# mission phase -> persistent physiological offsets
PHASE_DELTAS = {
    "orbit": {},
    "launch": dict(hr=+25, resp=+4, temp=+0.1),
    "eva": dict(hr=+32, resp=+8, temp=+0.4, rad=+0.5),
    "sleep": dict(hr=-9, resp=-3, temp=-0.3),
}


class Wearable:
    def __init__(self, astro_id):
        self.id = astro_id
        base = PROFILES.get(astro_id) or dict(hr=66, spo2=98.0, temp=36.6, resp=14, rad=0.35)
        self.base = dict(base)
        self.cur = dict(base)
        self.scenario = None
        self.scenario_until = 0.0
        self.fault_until = 0.0
        self.phase = random.random() * 6.28
        self.mission_phase = "orbit"

    def set_phase(self, name):
        if name in PHASE_DELTAS:
            self.mission_phase = name
            return True
        return False

    def trigger(self, name):
        if name == "sensor_fault":
            self.fault_until = time.time() + 12
            return True
        if name in SCENARIOS:
            self.scenario = name
            self.scenario_until = time.time() + SCENARIOS[name][1]
            return True
        return False

    def step(self) -> dict:
        now = time.time()
        if self.scenario and now > self.scenario_until:
            self.scenario = None
        target = dict(self.base)
        for k, d in PHASE_DELTAS[self.mission_phase].items():
            target[k] = target[k] + d
        if self.scenario:
            for k, d in SCENARIOS[self.scenario][0].items():
                target[k] = target[k] + d
        # circadian-ish slow drift + smoothing toward the target
        drift = math.sin(now / 90 + self.phase)
        target["hr"] += 2 * drift
        for k in self.cur:
            self.cur[k] += (target[k] - self.cur[k]) * 0.18
        noise = lambda s: random.gauss(0, s)
        v = {
            "hr": round(self.cur["hr"] + noise(1.2), 1),
            "spo2": round(min(100, self.cur["spo2"] + noise(0.25)), 1),
            "temp": round(self.cur["temp"] + noise(0.04), 2),
            "resp": round(max(4, self.cur["resp"] + noise(0.5)), 1),
            "radiation": round(max(0.0, self.cur["rad"] + noise(0.03)), 2),
        }
        if now < self.fault_until:  # broken sensor: implausible readings
            v["hr"] = 0.0
            v["spo2"] = 0.0
        return v
