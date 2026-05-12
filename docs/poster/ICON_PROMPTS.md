# Icon Prompts for Gender Classification Methods

> **Purpose:** Generate consistent method icons for the project poster.
> **Date:** 2025-02-28

---

## Shared Style Directive

Prepend this to **every** prompt to ensure visual consistency:

> **Style prefix:**
> `Flat minimalist icon, single centered symbol, thick rounded outlines, soft pastel background circle, no text, no letters, no labels, clean vector style, 1:1 aspect ratio, white background outside the circle, suitable for a scientific poster at small sizes (≈3 cm). Muted but distinct colour palette.`

---

## Method Prompts

### 1. GND (Ground Truth — Authority File Lookup)

**Concept:** Library catalog / authority file — the "gold standard" reference.

```
{style prefix} A small golden shield with a checkmark inside it, resting on an
open book. Colour accent: gold / warm amber circle background. Conveys
authority, trust, and verified knowledge.
```

---

### 2. gender-guesser (Dictionary Lookup)

**Concept:** Static name → gender dictionary, like flipping through an index.

```
{style prefix} A thick open book with a magnifying glass hovering over its
pages, a small list of names visible. Colour accent: teal / mint green circle
background. Conveys looking up entries in a reference book.
```

---

### 3. ClassifyGender / DistilBERT (Transformer Model)

**Concept:** A compact neural network — DistilBERT is a "distilled" transformer.

```
{style prefix} A small beaker or flask with a neural-network graph (3–4 nodes
and edges) visible inside the glass. Colour accent: electric blue / sky blue
circle background. Conveys a compact, distilled deep-learning model.
```

---

### 4. Genderize / BERT (Transformer Model)

**Concept:** Full-size BERT transformer — heavier than DistilBERT.

```
{style prefix} A layered stack of three horizontal transformer blocks (rounded
rectangles) with small connection lines between them, glowing softly. Colour
accent: indigo / deep purple circle background. Conveys a deep, multi-layer
neural network.
```

---

### 5. HIVOTO (Historical Name Dictionary)

**Concept:** A curated historical German first-name database linked to Wikidata.

```
{style prefix} An old parchment scroll partially unrolled, with a small clock
or hourglass beside it. Colour accent: warm sienna / sandstone circle
background. Conveys historical records, archival research, and temporal depth.
```

---

### 6. nomquamgender (Probabilistic Cultural-Consensus Model)

**Concept:** Aggregates multiple signals into a probability — "name rather than gender."

```
{style prefix} A bell curve (normal distribution) with a dashed vertical
threshold line, overlaid on a subtle crowd-of-dots motif. Colour accent:
coral / salmon pink circle background. Conveys statistical probability and
cultural consensus.
```

---

### 7. Wiki-Gendersort (Wikipedia-Derived Dictionary)

**Concept:** Large-scale name list extracted automatically from Wikipedia biographies.

```
{style prefix} A simplified Wikipedia globe (puzzle-sphere with a few jigsaw
seams) with a small sort/filter funnel below it. Colour accent: soft grey /
silver circle background. Conveys Wikipedia as source, with systematic
extraction.
```

---

### 8. LLM / oss-gpt (Large Language Model via Ollama)

**Concept:** A generative LLM that reads full biographical records and reasons over them.

```
{style prefix} A stylised chat bubble containing a small brain icon, with tiny
sparkle accents around it. Colour accent: warm orange / peach circle
background. Conveys conversational AI, reasoning, and generative intelligence.
```

---

## Colour Palette Summary

| Method              | Circle Colour         | Hex (suggestion) |
|---------------------|-----------------------|-------------------|
| GND (Ground Truth)  | Gold / Warm Amber     | `#F5C842`         |
| gender-guesser      | Teal / Mint Green     | `#5EC4A8`         |
| ClassifyGender      | Electric / Sky Blue   | `#4DA8DA`         |
| Genderize (BERT)    | Indigo / Deep Purple  | `#7B68AE`         |
| HIVOTO              | Sienna / Sandstone    | `#C9956B`         |
| nomquamgender       | Coral / Salmon Pink   | `#F08080`         |
| Wiki-Gendersort     | Soft Grey / Silver    | `#A8B2BD`         |
| LLM (oss-gpt)      | Warm Orange / Peach   | `#F4A261`         |

Each colour is distinct enough to serve as a secondary visual identifier on the poster even at small sizes or in black-and-white (varied lightness).

---

## Usage Notes

1. **Aspect ratio:** Generate at 1:1 (square). Recommended resolution: 1024 × 1024 px.
2. **Models tested with:** These prompts work well with DALL·E 3, Midjourney v6, and Stable Diffusion XL. For SD-based models, add `simple icon design, svg style` to the negative prompt to avoid excessive detail.
3. **Post-processing:** After generation, crop tightly to the circle and export as transparent PNG for overlay on the poster.
4. **Consistency check:** Generate all 8 in one batch/session if possible so the model maintains stylistic coherence.
5. **If the model adds text:** Re-roll or add `--no text` (Midjourney) or strengthen the `no text, no letters, no labels` directive.
