### Privacy & Disclaimer

**Protocōl is not a medical device.** It is a personal health-intelligence
dashboard built for a single user. Nothing in this app constitutes medical
advice, a diagnosis, a treatment recommendation, or a substitute for direct
care from a licensed clinician. All decisions about medications, supplements,
lab work, and lifestyle changes belong with you and your physician.

#### Reference ranges

Throughout the app you will see two kinds of ranges side-by-side:

- **Lab range** — the population reference range printed on Quest / LabCorp
  reports. These are derived from healthy adults in a wide age band and are
  intentionally permissive (the lab is trying not to flag normal variation
  as disease).
- **Optimal range** — tighter targets drawn from longevity, functional
  medicine, and athletic-performance literature (Attia *Outlive*, Levine
  PhenoAge, IFM 2024 ranges, NLA cardiovascular guidance, Endocrine Society
  hormonal targets). These are *opinions* about what an optimized middle-aged
  body looks like; they are not standard-of-care.

A value inside the lab range but outside the optimal range is flagged
"suboptimal," not "abnormal." Use it as a conversation primer.

#### Data flow

- All data lives **locally** under `data/<username>/`. Nothing is uploaded
  to a third-party server by Protocōl itself.
- The optional LLM integration sends the **deterministic summary** of your
  data to OpenAI for narrative rewriting. It does not transmit raw CSV files
  or PII beyond what is in that summary. If no `OPENAI_API_KEY` is set, no
  network call is made and the app runs entirely offline.
- Connected integrations (Strava, Apple HealthKit, GitHub) operate within
  their own privacy boundaries — review each provider's privacy policy.
- A daily sync job (`scripts/daily_sync.py`) reads + writes only inside
  `data/<username>/`.

#### Data retention & deletion

- The **Settings → Privacy** section provides per-category data exports
  (zip bundle) for the right-of-portability.
- To delete your data entirely, remove `data/<username>/`. In v1.5 there is
  no separate account state — deleting that directory removes everything.
- N=1 experiment definitions and action items are stored as JSON; they are
  included in the data export bundle.

#### Sharing data with a clinician

The **Clinician Summary** page produces a printable handout (markdown + PDF).
The intent is to give your physician one page of structured context for a
30-minute visit. The LLM-rewrite mode rewrites that same handout into
clinical-narrative voice without inventing values.

#### AI / LLM caveats

The optional LLM rewrite (Recommendations, Clinician Summary, Imports) is a
language model and can produce **incorrect, hallucinated, or invented values**
— including numbers that look authoritative but were never in your data. The
**deterministic markdown summary is always the source of truth.** Before
sharing an LLM-generated narrative with a clinician, or before acting on any
number you see in the LLM tab, verify it against the underlying Bloodwork,
Wearables, CGM, or Body Composition pages. If a value disagrees between the
LLM narrative and the deterministic tab, trust the deterministic tab.

#### Experimental nature of longevity optimization

Several of the foundations of this app are **evolving research, not
standard-of-care**:

- **PhenoAge** is calibrated on US population data and has known limits for
  younger, unusually fit, or non-Western individuals. Treat the absolute number
  with skepticism; trust the trend over multiple draws.
- **Zone 2 dose targets** (≥150–180 min/week) are a synthesis of athletic and
  longevity literature, not a clinical guideline.
- **"Optimal" ranges** throughout the app come from functional-medicine and
  longevity sources (Attia *Outlive*, Levine, IFM, NLA) that are tighter than
  the standard lab reference ranges your physician will use. They are not a
  consensus position of mainstream clinical medicine.
- **Protocol elements such as TRT and peptides** are off-label or research-grade
  for many of the use cases discussed here. They should only be initiated,
  dosed, or changed under the care of a qualified clinician.

Discuss any meaningful change in care — adding a supplement, starting TRT,
adjusting medications — with your physician before acting on what Protocōl
shows you.

#### Limits & known gaps

- Wearable HRV (Apple, WHOOP) is optical and noisier than ECG. Treat absolute
  values with skepticism; trust direction over time.
- PhenoAge is calibrated on a US population sample and may be less accurate
  for younger or unusually fit individuals.
- The N=1 / experiment framework cannot detect drug interactions, allergies,
  or pre-existing conditions outside what you have entered into the protocol.

#### Liability

By using Protocōl you accept that the maintainers provide no warranty of
fitness for any clinical purpose. The app is provided as-is, for the
personal use of the operator.
