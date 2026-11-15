"""Interface mapping from a clicked organ to the NASA research it relates to. This is a navigation aid, not a diagnosis:
research datasets do not measure each organ's current condition in any astronaut."""
ORGANS = {
    "heart": {"system": "cardiovascular", "osdr": "cardiovascular", "ntrs": "spaceflight cardiovascular adaptation astronaut", "images": "astronaut cardiovascular bio-monitor", "hrr": "cardiovascular"},
    "lungs": {"system": "respiratory", "osdr": "respiratory", "ntrs": "spaceflight pulmonary respiratory astronaut", "images": "astronaut respiratory ISS", "hrr": "respiratory"},
    "brain": {"system": "neurological", "osdr": "neurological", "ntrs": "spaceflight brain neurological astronaut", "images": "astronaut neurological study ISS", "hrr": "neurological"},
    "eyes": {"system": "vision", "osdr": "vision", "ntrs": "spaceflight associated neuro-ocular syndrome", "images": "ocular health fundoscope ISS", "hrr": "vision"},
    "bones": {"system": "bone", "osdr": "bone", "ntrs": "spaceflight bone loss astronaut", "images": "astronaut exercise ARED bone", "hrr": "bone"},
    "muscles": {"system": "muscle", "osdr": "muscle", "ntrs": "spaceflight muscle atrophy astronaut", "images": "astronaut exercise muscle ISS", "hrr": "muscle"},
    "kidneys": {"system": "renal", "osdr": "renal", "ntrs": "spaceflight kidney stones renal astronaut", "images": "kidney cells ISS", "hrr": "renal"},
}
LIMITATIONS = [
    "Selecting an organ is an interface representation. It does not imply a measured condition of that organ.",
    "OSDR studies are research datasets, many from animals or cells. The organism is shown for each result.",
    "Human OSDR studies have small cohorts (for example two or fourteen astronauts) and mostly omics data, not live vital signs.",
    "Nothing here is a diagnosis or a validated prediction.",
]
