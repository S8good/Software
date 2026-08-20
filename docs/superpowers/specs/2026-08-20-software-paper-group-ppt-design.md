# Software and Paper Group-Meeting Presentation Design

## 1. Purpose and Audience

Create a 15-minute Chinese group-meeting presentation that explains the paper's
scientific logic and shows how the NanoSense software turns that logic into a
repeatable acquisition, processing, validation, and archival workflow.

The audience is a research group familiar with spectroscopy and sensing, but
not necessarily familiar with the current software implementation. The deck
must therefore lead with scientific questions and use software screenshots as
evidence of reproducibility, not as a product tour.

## 2. Narrative Strategy

Use the approved interleaved structure:

`scientific question -> paper evidence -> software implementation -> next evidence`

The presentation contains 12 main slides and optional backup slides. Target
timing is approximately 2 minutes for motivation and workflow, 3 minutes for
experimental design and acquisition, 3 minutes for spectral processing, 4
minutes for modeling and validation, and 3 minutes for traceability and
conclusions.

## 3. Main Slide Storyboard

| Slide | Message | Primary visual | Layout |
| --- | --- | --- | --- |
| 1 | Paper and software address one reproducibility problem | Graphical Abstract crop plus title | C opening |
| 2 | Why paired references, full spectra, and grouped validation matter | Three-question schematic | A hybrid |
| 3 | The complete acquisition-to-archive workflow | Six-stage horizontal flow | Workflow band |
| 4 | NanoSense supports controlled acquisition and reference collection | Measurement GUI crop | B software |
| 5 | The paired AuNP/FTO design defines the validation unit | Figure 1 | A result |
| 6 | Processing methods and QC make spectral inputs auditable | Measurement QC and method controls | B software |
| 7 | Material structure and paired spectral response provide the signal basis | Figures 2 and 3 | A result |
| 8 | The software exposes preprocessing, peak analysis, and model entry points | Analysis GUI and LSPR workbench crops | B software |
| 9 | Calibration and grouped model comparison support quantitative prediction | Figures 4 and 5 | A result |
| 10 | Fusion prediction and robustness are the central performance evidence | Figure 7 | A result |
| 11 | Raw data, method versions, QC, and reanalysis remain traceable | Database Explorer and lineage schematic | B software |
| 12 | The paper result becomes a reusable analysis platform | Three-part takeaway and next steps | C closing |

Each slide has one sentence-length takeaway. Body text is limited to three
short bullets or labels; detailed explanations belong in speaker notes.

## 4. Visual System

Use a 16:9 white presentation with restrained scientific styling:

- Deep navy for headings and main text.
- Teal for software workflow and reproducibility annotations.
- Warm amber for experimental or model emphasis.
- Purple only as a small secondary accent for future work or uncertainty.
- Preserve the original colors of manuscript figures whenever possible.
- Use A (main figure plus right-side takeaway) for paper evidence, B (cropped
  interface plus numbered callouts) for software pages, and C (dark background
  with three takeaways) only for slides 1 and 12.

Figures should occupy about 60% of the slide area. Screenshots must be cropped
to the relevant panel and annotated with numbered callouts; full application
windows are reserved for the workflow overview or backup slides.

## 5. Asset Mapping

Primary manuscript assets are taken from `figure/*.png` and the corresponding
source-data notes under `data/figure_source_data/`. The main evidence set is:

- Graphical Abstract for the opening concept.
- Figure 1 for paired sensing and grouped validation workflow.
- Figures 2 and 3 for material structure and full-spectrum response.
- Figures 4 and 5 for calibration and model benchmarking.
- Figure 7 for fusion predictions and robustness.
- Figure S2 or S9 for optional QC and control diagnostics.

Software visuals should be captured from the current iteration build and focus
on the Measurement page, LSPR AI Workbench, Database Explorer, QC summary,
processing-method controls, and reanalysis entry point. Screenshots must use a
consistent window size and avoid showing personal paths or historical data.

## 6. Evidence and Wording Rules

- Do not invent numerical results that are not visible in the manuscript or
  verified source data.
- Keep conclusions scoped to the paper's within-dataset proof-of-concept
  evidence and state external validation as future work when appropriate.
- Distinguish clearly between an implemented software capability and a
  scientifically validated performance claim.
- Put sample size, grouping unit, and validation strategy near the relevant
  figure rather than in a dense methods slide.
- Present the database lineage feature as a reproducibility and auditability
  capability, not as evidence that the model is more accurate.

## 7. Deliverables and Acceptance Criteria

The implementation phase will produce:

1. An editable `.pptx` presentation with 12 main slides and a small backup
   section for additional figures or implementation details.
2. A rendered PDF or slide-image preview for visual QA.
3. A source-asset manifest mapping every figure and screenshot to its source.
4. Speaker notes containing a short talk track and the target time per slide.

Acceptance criteria:

- The complete deck can be presented in 15 minutes without reading paragraphs.
- Every main slide has one obvious visual focal point and one takeaway.
- Figure labels, axes, legends, and screenshot annotations remain readable at
  normal presentation scale.
- Paper claims, software capabilities, and future work are visually distinct.
- No text overlaps, clipped figures, unexplained abbreviations, or personal
  filesystem paths appear in the final deck.
- The editable PPTX and rendered preview have matching slide counts and order.
