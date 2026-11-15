# CipherPulse

Secure, real-time astronaut health monitoring with agentic AI, voice control, a realistic 3D mission console and a narrated guided tour for beginners.

## Start (one click)

**Windows:** double-click `start.bat`.
It finds Python (or installs it with winget), creates a virtual environment, installs everything on the first run, picks a free port automatically, starts the system and opens your browser.

**macOS / Linux:** run `./start.sh`.

Nothing else is needed. Close the window to stop. No API keys are required: without keys the AI explanations use built-in rules.

## For beginners: take the tour

Click **Guided tour** (top right). A narrated, video-style walkthrough with 17 chapters runs the real system: it cuts the link, forges packets, tampers with the vault and simulates a CO2 leak while explaining each step. Controls: pause, back, next, speed, chapter menu, click the progress bar to jump. The **Learn** tab explains every term in plain language.

## What is in the console

| Area | What it does |
|---|---|
| Crew view | Realistic PBR spacesuit astronaut with a live ECG on the chest. **Suit / X-ray / Holo** modes show bones and organs responding to live vitals |
| Orbit view | Earth with atmosphere, space station, and the radio link to ground control. The beam turns red when the link is cut and shows buffered packets |
| System view | Live 3D map of the pipeline: wearables, verifier, vault, analysis, AI agents, memory, LLM providers, dashboard, MCP and A2A |
| Live tab | Vitals with safe zones, alerts with AI explanations |
| Analytics tab | Crew comparison chart with alert markers, health index, radiation budget, early-warning forecasts |
| Security tab | Why packets were blocked, recent blocked packets, protections in use |
| Settings tab | Edit alert limits live, choose mission phase, sound, glow, graphics quality |
| Dock | Health scenarios, attacks, link control, mission phase, voice and text assistant |
| Header | Mission report (printable), CSV export |

## How it works

| Part | File | What it does |
|---|---|---|
| Wearables | `cipherpulse/sensor/` | Simulated vitals, Ed25519-signed packets, offline buffer, mission phases, attack hooks |
| Gateway | `cipherpulse/gateway/` | Verifies signature, replay, freshness, plausibility; AES-256-GCM vault with SHA-256 hash chain |
| Analysis | `cipherpulse/analysis/detector.py` | Phase-aware limits, rolling z-score, Isolation Forest, pattern correlator, trend forecast, health index |
| Agents | `cipherpulse/agents/graph.py` | LangGraph: recall, analyze (LLM), safety guard, memorize |
| LLM chain | `cipherpulse/agents/llm.py` | Claude, then Groq, then Gemini, then built-in rules |
| Memory | `cipherpulse/agents/memory.py` | Local SQLite; Mem0 if `MEM0_API_KEY` is set |
| MCP | `cipherpulse/agents/mcp_server.py` | `python -m cipherpulse.agents.mcp_server` exposes status, alerts, history, integrity check |
| A2A | `/.well-known/agent.json`, `POST /a2a` | Agent card and `message/send` |
| Console | `cipherpulse/web/` | `index.html`, `js/ui.js`, `js/scene.js`, `js/tour.js` |

## Real NASA data (NASA tab)
The **NASA** tab connects to official NASA sources, and every item carries a provenance label (`NASA_OBSERVED`, `NASA_RESEARCH`, `SIMULATED_DEMO`, `UNAVAILABLE`, ...).
- **Research explorer:** search NASA OSDR by body system, human studies first, see organism, files, formats; download and inspect small tabular files and ISA-Tab metadata ZIPs. Specialised formats (FASTQ, BAM, CEL, IDAT...) are listed with the tool needed, never parsed as CSV.
- **Space weather:** NASA DONKI flares, CMEs, SEPs and geomagnetic storms. These are events, never an astronaut's dose.
- **Images and reports:** NASA Image Library (with credits and NASA ids), NTRS reports, Human Research Roadmap, Environmental Data App status.
- **3D link:** in X-ray view click the heart, lungs, brain, eyes, bones, muscles or kidneys to open the related NASA research (an interface aid, not a diagnosis).
- **Important:** live vitals in this demo are `SIMULATED_DEMO`. No public live astronaut telemetry exists.

Set `NASA_API_KEY` in `.env` (free at https://api.nasa.gov/). To prove the integrations on your machine, double-click `validate_nasa.bat`. It downloads a real OSDR file and writes `data/nasa/validation_report.json`. See `docs/NASA_DATA_SOURCES.md` for exactly what has and has not been verified.

## Voice commands (Chrome or Edge)
"How is A2 doing?", "Who is most at risk?", "Radiation dose", "Verify integrity", "Show X-ray", "Show orbit", "Show system", "Select A3", "Start the tour", "Open the report", "Simulate CO2 on A2", "Set phase to EVA", "Cut the link".

## Add your API keys (optional)
Double-click `setup_keys.bat` after the first start. It asks for your NASA, Claude, Groq, Gemini and Mem0 keys, saves them only to the local `.env` file, and tests the NASA key. Press Enter to skip any key. Restart `start.bat` afterwards.
Keys are never stored in the project files, the zip or the browser code. If a key was ever pasted into a chat or shared, create a new one and replace it.

## Troubleshooting
- **Port busy:** nothing to do, a free port is chosen and printed in the window.
- **3D looks plain or slow:** Settings tab, set Graphics to Medium or Low, or untick Glow.
- **Earth looks simple:** the detailed Earth maps load from the internet; the procedural Earth is used offline.
- **No voice input:** use Chrome or Edge and allow the microphone.
- Run the tests: `.venv\Scripts\python -m pytest -q` (Windows) or `.venv/bin/python -m pytest -q`.

## Notes
- Simulated data. Prototype, not a medical device. Simulation clock: 1 real second is 1 simulated hour (used for radiation dose).
- three.js r128 is bundled in `cipherpulse/web/vendor/three` (MIT license, see `LICENSE-three.txt`) so the console works without a CDN.
- Optional Earth textures are fetched from the three.js examples repository; check their license before publishing a build that depends on them.
- Device private keys and the vault master key are generated in `data/` (git-ignored). For production use a TPM/HSM or secrets manager.
