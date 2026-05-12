# Quick Start Guide

## ⚡ 30-Second Setup

1. **Install dependencies**:

   ```bash
   pip install streamlit pandas plotly gender-guesser nomquamgender transformers torch requests
   ```

2. **Launch the app**:

   ```bash
   streamlit run src/gendertagger/prototype/app.py
   ```

3. **Import your data**:
   - Go to **Settings** tab
   - Click **Import Person Register**
   - Default path: `data/raw/schleiermacher/Register/Personen`

4. **Start annotating**!
   - **Browse & Annotate**: Filter and annotate systematically
   - **Game Mode**: Race against time for points!

## 🎮 Game Mode Quick Guide

1. Enter your name
2. Choose difficulty (Easy/Medium/Hard)
3. Click **Start New Game**
4. Click the correct gender:
   - ♂️ Male
   - ♀️ Female
   - 🏢 Institution
   - ⏭️ Skip (if unsure)

**Pro Tips**:

- Build streaks for bonus points!
- Hard mode = no classifier hints = more points
- Check leaderboard in Statistics

## 📊 Browse Mode Quick Guide

**Filters**:

- **Status**: All / Unannotated / Annotated / Uncertain
- **Gender**: All / Male / Female / Unknown / Institution
- **Search**: Type name to find specific persons

**Actions**:

- Click gender button to annotate
- Click 🗑️ to delete annotation
- Use pagination to navigate

## 🤖 Classifiers

The app shows predictions from up to 4 classifiers:

- **gender-guesser**: Fast, rule-based
- **nomquamgender**: Statistical model
- **hf-Gender-Classification**: AI/ML model
- **gnd-api**: Authority data (needs GND ID)

## 📤 Export Your Data

**Settings → Export**:

- **CSV**: Spreadsheet-compatible
- **JSON**: For further processing
- **TEI-XML**: (Coming soon) Enriched with annotations

## 🔧 Troubleshooting

| Problem                 | Solution                                           |
| ----------------------- | -------------------------------------------------- |
| App won't start         | `pip install -r requirements.txt`                  |
| "No persons found"      | Import data via Settings                           |
| Slow first startup      | Transformers downloading models (normal)           |
| Classifiers not loading | Check console for errors, use "Reload Classifiers" |

## 📁 File Locations

- **Database**: `data/output/annotations.db`
- **Source code**: `src/gendertagger/prototype/app.py`
- **Classifiers**: `src/gendertagger/backend/classification/gender.py`
- **XML parser**: `src/gendertagger/backend/data/extract.py`

## 🎯 Keyboard Shortcuts

_Within Streamlit:_

- `R` - Rerun app
- `Ctrl+Shift+R` - Clear cache and rerun
- `?` - Show keyboard shortcuts

## 💡 Tips & Tricks

1. **Bulk Import**: Place all XML files in one directory before importing
2. **Uncertain Cases**: Mark as "Uncertain" to review later (filter by Uncertain)
3. **Team Play**: Enter different names in Game Mode to compete
4. **Backup**: Export CSV regularly to backup your annotations
5. **Speed**: Use Game Mode to rapidly annotate easy cases

## 📞 Support

Check the documentation:

- `docs/UI_GUIDE.md` - Full user guide
- `docs/INTEGRATION.md` - Technical details
- `test_setup.py` - Run to diagnose issues

---

**Happy Annotating! 🎉**
