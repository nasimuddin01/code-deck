# Hardware experiments (archival)

The scripts that led to the working raw-USB transport in `turzx/usbraw.py`:
serial-driver A/B tests, byte-toxicity probes, vendor init replays, bulk-USB
staging tests. Kept for reference; they are not maintained.

`display.py` is the original pyserial/CDC driver (`TurzxScreen`) that these
scripts import — superseded by the raw-USB path because the macOS serial
driver corrupts frames. Run from the repo root with the venv, e.g.
`PYTHONPATH=tools/experiments:. .venv/bin/python tools/experiments/probe.py`.
