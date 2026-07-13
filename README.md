# Generalized Fuzzy Inference Engine

This repository is a lightweight, pure-Python implementation of a general-purpose Fuzzy Inference Engine. It evaluates fuzzy logic inputs based on a single unified YAML configuration file.

## Installation
The only requirement is `pyyaml` to parse the configuration files.

```bash
pip install -r requirements.txt
```

## How It Works
The `FuzzySystem` reads a `.yml` configuration file containing definitions for `inputs`, `outputs`, and `rules` (see `examples/clair_apt_base.yml` for an example of what this looks like).

It parses all membership functions (e.g., `trapmf`, `trimf`) natively and evaluates the min/max (AND/OR/NOT) fuzzy rules without external dependencies like `scipy`.

## CLI Interface
You can interact with the engine directly from the command line:

```bash
export PYTHONPATH=$(pwd)
python triggering/fuzzy.py compute --config "examples/clair_apt_base.yml" --inputs "{'L1_DOM': 1, 'L2C_AR': 1, 'TSIM': 0.3, 'TACC': 0.3, 'PACE': 5, 'TIME': 1200}"
```

## Python API
The system provides a straightforward API to embed into your projects:

```python
from triggering.fuzzy import FuzzySystem

# 1. Instantiate the system with your unified configuration
engine = FuzzySystem(config_path="examples/clair_apt_base.yml")

# 2. Provide crisp inputs as a dictionary
state = {
    'L1_DOM': 1.0,
    'L2C_AR': 1.0,
    'TSIM': 0.3,
    'TACC': 0.3,
    'PACE': 5.0,
    'TIME': 1200.0
}

# 3. Compute and retrieve outputs
fuzzy_outputs = engine.compute(state)
print(fuzzy_outputs)
```

## Running Tests
Run the included test suite to verify the generic inference engine correctly evaluates inputs against rules:
```bash
python -m unittest tests/test_triggering.py
```
