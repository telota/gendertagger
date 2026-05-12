# TEI Gender Annotator - Integrated Version

A gamified web application for annotating gender in TEI-XML person registers.

## 🎯 Features

- **Browse & Annotate Mode**: Browse persons with filtering, search, and pagination
- **Game Mode**: Gamified annotation with scoring, streaks, and leaderboards
- **Statistics Dashboard**: Visual analytics and progress tracking
- **Settings**: Import/export data, manage classifiers
- **Multiple Classifiers**: Uses 4 different gender classification approaches
  - gender-guesser (rule-based)
  - nomquamgender (statistical)
  - HuggingFace transformers (ML-based)
  - GND API (authority data)

## 📁 Project Structure

```
gendertagger/
├── src/
│   └── gendertagger/
│       ├── backend/
│       │   ├── classification/
│       │   │   ├── gender.py          # All classifiers
│       │   │   └── utils.py
│       │   ├── config/
│       │   │   └── base.py            # Configuration
│       │   ├── data/
│       │   │   ├── extract.py         # TEI-XML parser
│       │   │   └── enrich.py          # Data enrichment
│       │   ├── llm/
│       │   │   ├── client.py          # LLM client
│       │   │   ├── prompts.py         # Prompt templates
│       │   │   └── schemas.py         # Response schemas
│       │   ├── transformations/
│       │   │   └── reformat.xslt      # XSLT transformations
│       │   └── utils/
│       │       └── embeddings.py      # Embedding utilities
│       ├── frontend/                  # Frontend (planned)
│       └── prototype/
│           ├── app.py             # Main Streamlit app
│           └── database.py        # SQLite manager
├── data/
│   ├── output/
│   │   ├── annotations.db             # SQLite database (created automatically)
│   │   └── results/                   # Classification results
│   ├── processed/                     # Processed datasets
│   └── raw/
│       └── schleiermacher/Register/Personen/  # Your TEI-XML files
└── requirements.txt
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:

- streamlit >= 1.28
- pandas >= 2.0
- plotly >= 5.17
- gender-guesser >= 0.4
- nomquamgender >= 0.1
- transformers >= 4.30
- torch >= 2.0
- requests

### 2. Launch the App

**Option A: Command line**

```bash
streamlit run src/gendertagger/prototype/app.py
```

### 3. Import Your Data

1. Go to **Settings** tab
2. Enter path to your person register directory
3. Click **Import Person Register**

Default path: `data/raw/schleiermacher/Register/Personen`

## 📖 Usage Guide

### Browse & Annotate Mode

- **Filter** by annotation status, gender, or search by name
- **View** person details and classifier predictions
- **Annotate** with one click: ♂️ Male, ♀️ Female, 🏢 Institution, ❓ Uncertain
- **Delete** annotations with 🗑️ button

### Game Mode

1. Enter your name
2. Select difficulty (Easy/Medium/Hard)
3. Click **Start New Game**
4. Annotate as fast as you can!
5. Earn points and climb the leaderboard

**Scoring:**

- Base: 10 points per annotation
- Streak bonus: +2 points per consecutive correct answer
- Time bonus: Up to +10 points for speed

### Statistics

View:

- Overall progress (completion percentage)
- Gender distribution (pie chart)
- Leaderboard (top 10 players)

### Settings

- **Import**: Load TEI-XML person registers
- **Export**: Download annotations as CSV or JSON
- **Classifiers**: View loaded classifiers and reload if needed

## 🤖 Classifiers

### Gender Guesser

- Rule-based, uses name database
- Fast, good for Western names
- Confidence: High (95%) or Medium (70%)

### Nomquam Gender

- Statistical model
- Good international coverage
- Confidence: ~80%

### HuggingFace Transformer

- ML model: `padmajabfrl/Gender-Classification`
- Deep learning approach
- Variable confidence based on input

### GND API

- Queries German National Library authority data
- 100% confidence when available
- Requires GND ID in person data

## 💾 Database Schema

The app uses SQLite with 4 tables:

### `persons`

- Person data from TEI-XML
- Fields: xml_id, name, forename, surname, birth_date, death_date, notes, gnd_id

### `annotations`

- Human annotations
- Fields: person_xml_id, human_gender, annotator_name, is_uncertain, annotation_time

### `classifier_results`

- Automated predictions
- Fields: person_xml_id, classifier_name, predicted_gender, confidence

### `leaderboard`

- Game scores
- Fields: player_name, score, time_seconds, questions_answered

## 📤 Export Options

### CSV Export

Downloads a CSV file with all persons and annotations, including:

- Person details
- Annotation status
- Annotator name
- Uncertainty flag

### JSON Export

Downloads structured JSON with the same data, useful for further processing.

### TEI-XML Export (Coming Soon)

Will export enriched TEI-XML with @sex attributes added based on annotations.

## 🔧 Customization

### Adding a New Classifier

1. Open `src/gendertagger/backend/classification/gender.py`
2. Create a new class inheriting from `GenderClassifier`
3. Implement `predict()` and `name` property
4. Add to `get_available_classifiers()`

Example:

```python
class MyCustomClassifier(GenderClassifier):
    @property
    def name(self) -> str:
        return "my-classifier"

    def predict(self, person_data: Dict[str, str]) -> Tuple[str, float]:
        # Your logic here
        return ('male', 0.85)
```

### Changing Database Location

Edit `init_database()` in `src/gendertagger/prototype/database.py`:

```python
db_path = Path("/your/custom/path/annotations.db")
```

## 🐛 Troubleshooting

### "No module named 'streamlit'"

```bash
pip install streamlit
```

### "No module named 'gender_guesser'"

```bash
pip install gender-guesser nomquamgender
```

### "No module named 'transformers'"

```bash
pip install transformers torch
```

### Classifier Loading Errors

- Check console for specific error messages
- Some classifiers are optional (app will work without them)
- Use "Reload Classifiers" button in Settings

### Import Errors

- Verify XML files are valid TEI-XML
- Check that files contain `<person>` elements with namespace `http://www.tei-c.org/ns/1.0`
- Look for error messages in the console

## 📊 Performance

- **Startup**: 3-5 seconds (loading classifiers)
- **Import**: ~100-500 persons/second
- **Annotation**: Instant save
- **Game Mode**: Smooth, no lag

## 🔐 Data Privacy

- All data is stored locally in SQLite
- No external API calls except GND classifier (optional)
- No tracking or telemetry

## 📝 License

Part of the Schleiermacher Edition project.

## 👥 Credits

- Built with Streamlit
- Classifiers: gender-guesser, nomquamgender, HuggingFace
- GND API: German National Library
