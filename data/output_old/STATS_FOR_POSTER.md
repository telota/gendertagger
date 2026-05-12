# Stats for Poster — genderTagger

> Source: `data/raw/Register/Personen/*.xml` (26 files, A–Z)
> Parsed: 2026-02-23

## "Before" — Current State of the Register

| Metric                        | Value   |
|-------------------------------|---------|
| Total `<person>` elements     | 8,273   |
| With GND URI (`idno type="uri"`) | 2,632   |
| Without GND                   | 5,641   |
| With `sex` attribute          | 0       |
| `<listPerson>` groups (families etc.) | 959 |
| Special roles (mythological)  | 2       |

### Notes
- The register is **completely unannotated** — no `@sex` attributes exist.
- GND URIs follow the pattern `https://d-nb.info/gnd/{id}`
- The poster previously stated "8093 Personen" — this was from an older snapshot; the register has since grown by ~180 entries.
- The old `output/persons_with_gender_20251022_221528.csv` had 12,110 rows / 11,457 unique IDs due to duplicate extraction from nested `<listPerson>` groups.

## "After" — GND Ground Truth

> Source: `output/ground_truth.db` — built via `src/build_ground_truth.py`
> API: lobid.org/gnd | Queried: 2026-02-23

### GND API Query Summary

| Metric                              | Value   |
|-------------------------------------|---------|
| Persons with GND URI                | 2,632   |
| Unique GND IDs queried              | 2,600   |
| Successful responses (HTTP 200)     | 2,597   |
| Failed responses (HTTP 404)         |     3   |
| Persons with GND but missing query  |     0   |

### Gender Distribution — GND Ground Truth (unique GND IDs)

| Gender   | Count | % of queried |
|----------|------:|-------------:|
| Male     | 2,030 |        78.2% |
| Female   |   190 |         7.3% |
| Unknown  |   377 |        14.5% |
| Error    |     3 |         0.1% |
| **Total**| **2,600** |    **100%** |

### Gender Distribution — at Person Level (GND IDs mapped back to register)

| Gender   | Persons |
|----------|--------:|
| Male     |   2,048 |
| Female   |     204 |
| Unknown  |     377 |
| Error    |       3 |
| **Total**| **2,632** |

> 32 persons share a GND ID with another person entry (duplicate GND URIs in the register).
> Binary gender (m/f) coverage of GND-queried persons: **2,220 / 2,597 = 85.5%**

### GND Entity Types (top 5, among gendered responses)

| GND Type                                  | Count |
|-------------------------------------------|------:|
| Person, DifferentiatedPerson              | 1,262 |
| DifferentiatedPerson, Person              | 1,246 |
| Person, RoyalOrMemberOfARoyalHouse        |    27 |
| RoyalOrMemberOfARoyalHouse, Person        |    26 |
| Person, LiteraryOrLegendaryCharacter      |    11 |

### Coverage Overview

| Segment                       | Persons | Gender known (m/f) | % coverage |
|-------------------------------|--------:|-------------------:|-----------:|
| With GND URI                  |   2,632 |              2,252 |      85.6% |
| Without GND                   |   5,641 |                  — |          — |
| **Total register**            | **8,273** |        **2,252** |   **27.2%** |

### Still TODO
- [ ] Run all classifiers on remaining 5,641 persons without GND
- [ ] Compute gender distribution for non-GND persons (name-based classifiers)
- [ ] Compute agreement metrics across classifiers
- [ ] Use GND ground truth as benchmark to evaluate classifier accuracy

=======================================================
LOADED FILES
=======================================================
  GND    :  8,273 rows
  gg     :  8,273 rows
  hfgc   :  8,273 rows
  hfg    :  8,273 rows
  hv     :  8,273 rows
  xgb    :  8,273 rows
  nqg    :  8,273 rows
  wgs    :  8,273 rows
  llm    :  8,273 rows

Combined DataFrame: 8,273 rows × 10 columns
     xml_id gnd_gender_mapped gg_gender hfgc_gender hfg_gender hv_gender xgb_gender nqg_gender wgs_gender llm_gender
0  S0000534            no_gnd   no_name     no_name    no_name   no_name    no_name    no_name    no_name       male
1  S0001040            no_gnd      male        male       male      male       male       male       male       male
2  S0001041              male      male        male       male      male       male       male       male       male
3  S0001042            no_gnd      male        male       male      male       male       male       male       male
4  S0001043              male      male        male       male      male       male       male       male       male

=======================================================
1. GROUND TRUTH (GND)
=======================================================
  Total GND records        :  8,273
    no GND match           :  5,643
    GND gender = unknown   :    377
    GND gender = male      :  2,047
    GND gender = female    :    203
  Ground truth subset size :  2,250  (male + female only)

=======================================================
2. COVERAGE STATISTICS PER METHOD
=======================================================
                   Total  Classified  Ambiguous  Failed/no_name  Coverage %
Method
gender_guesser      8273        5603        530            2140        67.7
HF ClassifyGender   8273        5685        448            2140        68.7
HF Genderize        8273        5577        556            2140        67.4
HIVOTO              8273        5816        317            2140        70.3
HIVOTO-XGBoost      8273        6001         27            2245        72.5
NQG                 8273        5758        375            2140        69.6
Wiki-Gendersort     8273        5748        326            2199        69.5
LLM                 8273        7399        874               0        89.4

=======================================================
3. CLASSIFICATION DISTRIBUTION (counts)
=======================================================
                   male  female  conflict  unknown  uncertain  unisex  andy  mostly_male  mostly_female  no_name  NaN/missing
Method
gender_guesser     4327    1276       115      408          0       0     1            6              0     2140            0
HF ClassifyGender  4570    1115       448        0          0       0     0            0              0     2140            0
HF Genderize       4653     924       556        0          0       0     0            0              0     2140            0
HIVOTO             4372    1444        38      176          0       0    50           42             11     2140            0
HIVOTO-XGBoost     4487    1514         0        0          0       0    27            0              0     2245            0
NQG                4380    1378        33      217        125       0     0            0              0     2140            0
Wiki-Gendersort    4458    1290       178      102          0      46     0            0              0     2199            0
LLM                5466    1933         0      483          0       0     0            0              0        0            0

=======================================================
4. PRECISION ON GND GROUND TRUTH
=======================================================
                   GT records  Classified  Ambiguous  Failed/no_name  Correct  Accuracy %  Correct male  Correct female
Method
gender_guesser           2250        1986         89             175     1977        99.5          1805             172
HF ClassifyGender        2250        1975        100             175     1947        98.6          1804             143
HF Genderize             2250        1980         95             175     1946        98.3          1825             121
HIVOTO                   2250        1999         76             175     1998        99.9          1813             185
HIVOTO-XGBoost           2250        2070          5             175     2055        99.3          1868             187
NQG                      2250        2027         48             175     2026       100.0          1847             179
Wiki-Gendersort          2250        2004         71             175     1993        99.5          1821             172
LLM                      2250        2247          3               0     2244        99.9          2041             203

  Per-class correct:
    gender_guesser          male=1,805  female=  172
    HF ClassifyGender       male=1,804  female=  143
    HF Genderize            male=1,825  female=  121
    HIVOTO                  male=1,813  female=  185
    HIVOTO-XGBoost          male=1,868  female=  187
    NQG                     male=1,847  female=  179
    Wiki-Gendersort         male=1,821  female=  172
    LLM                     male=2,041  female=  203

=======================================================
5. SUMMARY
=======================================================
                   Classified  Ambiguous  Failed/no_name  Coverage %  GT records  Correct on GT  Accuracy on GT %
Method
gender_guesser           5603        530            2140        67.7        2250           1977              99.5
HF ClassifyGender        5685        448            2140        68.7        2250           1947              98.6
HF Genderize             5577        556            2140        67.4        2250           1946              98.3
HIVOTO                   5816        317            2140        70.3        2250           1998              99.9
HIVOTO-XGBoost           6001         27            2245        72.5        2250           2055              99.3
NQG                      5758        375            2140        69.6        2250           2026             100.0
Wiki-Gendersort          5748        326            2199        69.5        2250           1993              99.5
LLM                      7399        874               0        89.4        2250           2244              99.9

=======================================================
6. MISCLASSIFICATIONS ON GND GROUND TRUTH
=======================================================
                   Answered  Wrong total  Error %  Male→Female  Female→Male
Method
gender_guesser         1986            9      0.5            3            6
HF ClassifyGender      1975           28      1.4           12           16
HF Genderize           1980           34      1.7           10           24
HIVOTO                 1999            1      0.1            1            0
HIVOTO-XGBoost         2070           15      0.7           14            1
NQG                    2027            1      0.0            1            0
Wiki-Gendersort        2004           11      0.5            4            7
LLM                    2247            3      0.1            3            0

Plot saved → output/benchmark_coverage_accuracy.png
Plot saved → output/benchmark_distribution.png

=======================================================
7. INTER-ANNOTATOR AGREEMENT
=======================================================

--- Pairwise Cohen's Kappa ---
     Classifier 1      Classifier 2    N  Cohen's Kappa Interpretation
           HIVOTO    HIVOTO-XGBoost 6024          0.891 Almost perfect
   HIVOTO-XGBoost               NQG 6024          0.880 Almost perfect
           HIVOTO               NQG 6133          0.879 Almost perfect
   gender_guesser   Wiki-Gendersort 6074          0.870 Almost perfect
   gender_guesser               NQG 6133          0.870 Almost perfect
           HIVOTO   Wiki-Gendersort 6074          0.862 Almost perfect
   gender_guesser            HIVOTO 6133          0.851 Almost perfect
   HIVOTO-XGBoost   Wiki-Gendersort 5983          0.833 Almost perfect
   gender_guesser    HIVOTO-XGBoost 6024          0.821 Almost perfect
              NQG   Wiki-Gendersort 6074          0.820 Almost perfect
HF ClassifyGender      HF Genderize 6133          0.801 Almost perfect
   HIVOTO-XGBoost               LLM 6028          0.777    Substantial
HF ClassifyGender   Wiki-Gendersort 6074          0.761    Substantial
              NQG               LLM 6133          0.754    Substantial
           HIVOTO               LLM 6133          0.734    Substantial
HF ClassifyGender    HIVOTO-XGBoost 6024          0.732    Substantial
   gender_guesser HF ClassifyGender 6133          0.710    Substantial
     HF Genderize   Wiki-Gendersort 6074          0.700    Substantial
  Wiki-Gendersort               LLM 6074          0.699    Substantial
   gender_guesser               LLM 6133          0.695    Substantial
HF ClassifyGender            HIVOTO 6133          0.691    Substantial
HF ClassifyGender               NQG 6133          0.687    Substantial
     HF Genderize    HIVOTO-XGBoost 6024          0.666    Substantial
   gender_guesser      HF Genderize 6133          0.641    Substantial
     HF Genderize            HIVOTO 6133          0.626    Substantial
HF ClassifyGender               LLM 6133          0.624    Substantial
     HF Genderize               NQG 6133          0.621    Substantial
     HF Genderize               LLM 6133          0.564       Moderate

--- Global Agreement ---
  Fleiss' Kappa          = 0.768   [Substantial]    (N=5,983 rows where all methods answered)
  Krippendorff's Alpha   = 0.748   [Tentative conclusions only (0.667–0.800)]    (N=8,273 items)
  Cohen's Kappa (average)= 0.752   [Substantial]

Computing per-record metrics...

=================================================================
AGREEMENT TIER DISTRIBUTION
=================================================================
  unanimous            :  4,447  ( 53.8%)  ██████████████████████████
  strong_majority      :    840  ( 10.2%)  █████
  weak_majority        :    594  (  7.2%)  ███
  no_consensus         :    256  (  3.1%)  █
  single_rater         :  2,136  ( 25.8%)  ████████████
  no_answer            :      0  (  0.0%)

=================================================================
FLEISS' PER-ITEM AGREEMENT  P_i  (N = 8,273 records with ≥1 answer)
=================================================================
  Mean   = 0.9187
  Median = 1.0000
  Std    = 0.1767
  Min    = 0.0000
  Max    = 1.0000

  Distribution of P_i:
    0.0–0.2 :      4  (  0.0%)
    0.2–0.4 :    223  (  2.7%)
    0.4–0.6 :    623  (  7.5%)
    0.6–0.8 :    840  ( 10.2%)
    0.8–1.0 :  6,583  ( 79.6%)

=================================================================
SHANNON ENTROPY  H_i  (0 = consensus, max = 3.000 for 8 categories)
=================================================================
  Mean   = 0.1619
  Median = 0.0000
  Std    = 0.3469
  Min    = 0.0000
  Max    = 1.5613

=================================================================
MAJORITY VOTE BREAKDOWN  (records with ≥ 2 answers: 6,137)
=================================================================
  8/8 agree :  4,447 records  (male: 3,683, female: 764)
  7/8 agree :    840 records  (male: 521, female: 314, ambiguous: 5)
  6/8 agree :    306 records  (female: 170, male: 116, ambiguous: 20)
  5/8 agree :    175 records  (male: 98, female: 42, ambiguous: 35)
  4/8 agree :    334 records  (ambiguous: 154, male: 130, female: 50)
  3/8 agree :     31 records  (ambiguous: 23, female: 5, male: 3)
  1/8 agree :      4 records  (female: 2, male: 2)

=================================================================
TOP 20 MOST DISAGREED RECORDS  (highest entropy, ≥ 3 answers)
=================================================================
  xml_id                     forename  n_answered majority_label  majority_count  fleiss_P_i  entropy         tier gg_gender_norm hfgc_gender_norm hfg_gender_norm hv_gender_norm xgb_gender_norm nqg_gender_norm wgs_gender_norm llm_gender_norm
S0001384 (Stiefvater der Antonie von)           8         female               3      0.2500   1.5613 no_consensus         female           female            male      ambiguous          female       ambiguous       ambiguous            male
S0001502                  Baronin von           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous             male            male      ambiguous            male          female       ambiguous          female
S0002513                  Fürstin von           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous             male            male      ambiguous            male          female       ambiguous          female
S0003498          (Sohn der Frau von)           8           male               3      0.2500   1.5613 no_consensus      ambiguous             male            male         female          female       ambiguous          female            male
S0004522                      Alville           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous           female            male      ambiguous          female          female       ambiguous            male
S0762142 (erste Tochter des Ernst M.)           8           male               3      0.2500   1.5613 no_consensus           male        ambiguous            male      ambiguous          female       ambiguous            male          female
S1121685                         Haus           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous           female            male           male            male       ambiguous          female       ambiguous
S1121900                 Gabriele von           8         female               3      0.2500   1.5613 no_consensus         female             male            male      ambiguous          female       ambiguous       ambiguous          female
S2686802        (Sohn der Frau Scilô)           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous        ambiguous            male         female          female       ambiguous          female            male
S3405339                   "Fräulein"           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous             male            male      ambiguous            male       ambiguous          female          female
S7242627          Ulrike Theodore von           8      ambiguous               3      0.2500   1.5613 no_consensus      ambiguous             male            male         female          female       ambiguous       ambiguous          female

=================================================================
AGREEMENT BY MAJORITY LABEL
=================================================================
  male        : N=4,553  mean P_i=0.929  mean H=0.143  unanimous=3,683 (80.9%)
  female      : N=1,347  mean P_i=0.841  mean H=0.321  unanimous=764 (56.7%)
  ambiguous   : N=  237  mean P_i=0.424  mean H=1.073  unanimous=0 (0.0%)

Plot saved → output/record_agreement_distributions.png
Plot saved → output/record_agreement_tiers.png

  Total persons in register: 8,273

======================================================================
CLASSIFICATION DISTRIBUTION PER METHOD
======================================================================

Absolute counts:
               gender_guesser  HF ClassifyGender  HF Genderize  HIVOTO  HIVOTO-XGBoost   NQG  Wiki-Gendersort   LLM
male                     4327               4570          4653    4372            4487  4380             4458  5466
female                   1276               1115           924    1444            1514  1378             1290  1933
mostly_male                 6                  0             0      42               0     0                0     0
mostly_female               0                  0             0      11               0     0                0     0
organisation                0                  0             0       0               0     0                0   391
conflict                  115                448           556      38               0    33              178     0
unknown                   408                  0             0     176               0   217              102   483
uncertain                   0                  0             0       0               0   125                0     0
andy                        1                  0             0      50              27     0                0     0
unisex                      0                  0             0       0               0     0               46     0
no_answer                2140               2140          2140    2140            2245  2140             2199     0

Percentages:
               gender_guesser  HF ClassifyGender  HF Genderize  HIVOTO  HIVOTO-XGBoost   NQG  Wiki-Gendersort   LLM
male                     52.3               55.2          56.2    52.8            54.2  52.9             53.9  66.1
female                   15.4               13.5          11.2    17.5            18.3  16.7             15.6  23.4
mostly_male               0.1                0.0           0.0     0.5             0.0   0.0              0.0   0.0
mostly_female             0.0                0.0           0.0     0.1             0.0   0.0              0.0   0.0
organisation              0.0                0.0           0.0     0.0             0.0   0.0              0.0   4.7
conflict                  1.4                5.4           6.7     0.5             0.0   0.4              2.2   0.0
unknown                   4.9                0.0           0.0     2.1             0.0   2.6              1.2   5.8
uncertain                 0.0                0.0           0.0     0.0             0.0   1.5              0.0   0.0
andy                      0.0                0.0           0.0     0.6             0.3   0.0              0.0   0.0
unisex                    0.0                0.0           0.0     0.0             0.0   0.0              0.6   0.0
no_answer                25.9               25.9          25.9    25.9            27.1  25.9             26.6   0.0

======================================================================
COVERAGE TIERS PER METHOD
======================================================================
                   Male  Female  Leaning (m/f)  Organisation  Ambiguous  No answer Binary cov. Substantive cov. Any answer
Method
gender_guesser     4327    1276              6             0        524       2140       67.7%            67.8%      74.1%
HF ClassifyGender  4570    1115              0             0        448       2140       68.7%            68.7%      74.1%
HF Genderize       4653     924              0             0        556       2140       67.4%            67.4%      74.1%
HIVOTO             4372    1444             53             0        264       2140       70.3%            70.9%      74.1%
HIVOTO-XGBoost     4487    1514              0             0         27       2245       72.5%            72.5%      72.9%
NQG                4380    1378              0             0        375       2140       69.6%            69.6%      74.1%
Wiki-Gendersort    4458    1290              0             0        280       2199       69.5%            69.5%      73.4%
LLM                5466    1933              0           391        483          0       89.4%            94.2%     100.0%

Plot saved → output/coverage_tiers.png
Plot saved → output/coverage_distribution.png
Distribution CSV → output/coverage_distribution.csv