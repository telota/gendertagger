# genderTagger

A playful RSE tool for gender annotation in Digital Humanities projects.

**genderTagger** is a web-based application for gender classification in TEI-XML person registers. It combines **multiple automated classification methods** with a **gamified web interface** for human annotation, developed by TELOTA's [KI-Lab](https://www.bbaw.de/bbaw-digital/ki) and the [Gender & Data](https://www.bbaw.de/gender-data) initiative at the Berlin-Brandenburg Academy of Sciences and Humanities (BBAW).

## Overview

Person registers are the backbone of digital scholarly editions — they link actors, create context, and open perspectives on social and intellectual networks. Yet gender information is often missing, making the **Gender Data Gap** invisible. genderTagger addresses this by providing:

- **9 classification methods** ranging from authority file lookups to transformer models and local LLMs
- **A gamified web UI** with browse/annotate mode, a timed game mode with scoring and leaderboards, and statistics dashboards
- **TEI-XML import/export** so enriched data flows back into existing edition workflows
- **Benchmark tooling** to evaluate and compare classifier performance

The primary development case study is _schleiermacher digital_, whose person register contains ~8,000 entries.

## Quick Start

1. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```


[TODO]


## Classification Methods

genderTagger ships with nine independent classification approaches:

| Method                       | Type                         | Source / Model                                                                                                                        |
| ---------------------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **GND API**                  | Authority file lookup        | [lobid-gnd](https://lobid.org/gnd) (Gemeinsame Normdatei)                                                                             |
| **GND Local Lookup**         | Authority file (offline)     | Pre-built SQLite DB from GND MARC XML                                                                                                 |
| **gender-guesser**           | Rule-based heuristic         | [`gender-guesser`](https://pypi.org/project/gender-guesser/) library                                                                  |
| **nomquamgender**            | Statistical ML               | [`nomquamgender`](https://pypi.org/project/nomquamgender/) library                                                                    |
| **HF Gender-Classification** | DistilBERT transformer       | [`padmajabfrl/Gender-Classification`](https://huggingface.co/padmajabfrl/Gender-Classification)                                       |
| **HF Genderize**             | BERT transformer             | [`imranali291/genderize`](https://huggingface.co/imranali291/genderize)                                                               |
| **HIVOTO**                   | Historical name lookup       | [HIVOTO v1.0.0](https://www.geschichte.hu-berlin.de/de/bereiche-und-lehrstuehle/digital/forschung/hivoto) (Historisches Vornamentool) |
| **HIVOTO-XGBoost**           | XGBoost + char n-gram TF-IDF | Trained on HIVOTO dataset                                                                                                             |
| **LLM (Ollama)**             | Local large language model   | Configurable model via Ollama REST API                                                                                                |

Five of these classifiers (gender-guesser, nomquamgender, HF Gender-Classification, GND API, and optionally Ollama LLM) are integrated directly into the web UI to assist human annotators.

All nine methods were first developed and tested as **standalone scripts** (in `methods/`) to validate their accuracy and coverage independently before integration.

## Architecture

### Planned: FastAPI + Vue.js

The project is being refactored into a decoupled client-server architecture:

- **Backend** (`src/gendertagger/backend/`) — a **FastAPI** REST API exposing classification endpoints, TEI-XML import/export, annotation management, and user/session handling. All nine classifiers will be accessible through a unified API.
- **Frontend** (`src/gendertagger/frontend/`) — a **Vue.js** single-page application providing the gamified annotation UI, statistics dashboards, and team leaderboards.

This separation enables independent scaling, easier testing, and a richer interactive frontend.

## Project Structure


[TODO]



## Benchmark and Evaluation

The `scripts/` directory provides tools for systematic evaluation:

- **benchmark.py** — compares all nine methods against GND as ground truth; computes coverage, classification distributions, and accuracy metrics
- **agreements.py** — inter-annotator agreement: pairwise Cohen's κ, Fleiss' κ, Krippendorff's α
- **coverage.py** — coverage and classification distribution report across three tiers (binary, substantive, overall)

Poster visualisation scripts (`poster_benchmark_chart.py`, `poster_pies.py`, `poster_example_badges.py`) generate figures for presentations.

## Installation

### Requirements


[TODO]


### Setup


[TODO]


## Limitations

- Gender classification is based on historical names and uses a binary scheme (Male / Female) plus the categories Uncertain and Institution. Non-binary, trans\*, or agender categories are not currently supported.
- Name-based classification has inherent limitations and cultural biases.
- Classifications represent a statistical estimate and do not reflect individual gender identity.
- Results require validation, especially for ambiguous or culturally diverse names.

## Research Context

This work was presented at **deRSE26** (German Conference on Research Software Engineering, University of Stuttgart, March 3–5, 2026). The submitted abstract is available [here](https://events.hifis.net/event/2945/contributions/21353/).

## Contributing

This project is part of ongoing research. For questions or collaboration inquiries, please open an issue or contact the project team.

## License

This project is licensed under the [MIT License](LICENSE).

Copyright (c) 2026 TELOTA – The Electronic Life Of The Academy.

## Acknowledgments

Developed by the [KI-Lab](https://www.bbaw.de/bbaw-digital/ki) and [Gender & Data](https://www.bbaw.de/gender-data) initiative at TELOTA, Berlin-Brandenburg Academy of Sciences and Humanities (BBAW).

## Further Documentation

- [docs/references/](docs/references/) — reference documentation for tools and APIs
