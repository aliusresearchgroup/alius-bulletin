# Speaker Source Audit

This audit tracks hard-to-source profiles and false positives to avoid when
building F5-TTS reference clips. `candidate_ready` means a natural-voice source
candidate exists but still needs listening review before final rendering.

## Confirmed During Current Pass

| Speaker slug | Display name | Source | Status |
| --- | --- | --- | --- |
| `andrea_ciaunica` | Anna Ciaunica | Local deployed ALIUS MP3: `aliusresearch.org-audio-deploy-20260603/site-src/static/media/audio/bulletin/what-is-it-like-to-be-in-early-sensory-life-anna-ciaunica.mp3` | `candidate_ready` |
| `arnaud_halloy` | Arnaud Halloy | Canal-U conference page: `https://www.canal-u.tv/chaines/mshs-sud-est/jecis-journees-d-etudes-cognition-information-et-societe-2023/l-hypothese-des` | `candidate_ready` |
| `edvard_aviles` | Edvard Aviles | PUCP Educast page: `https://educast.pucp.edu.pe/video/7763/xii_simposio_de_estudiantes_de_filosofia_de_la_pucp__parte_4` | `candidate_ready` |
| `jakub_limanowski` | Jakub Limanowski | Direct MP3: `https://verein-radio98eins.de/wp-content/uploads/2024/07/E31_Biologische%20Psychologie_Podcast.mp3` | `candidate_ready` |
| `juan_gonzalez` | Juan Gonzalez | Local deployed ALIUS MP3: `aliusresearch.org-audio-deploy-20260603/site-src/static/media/audio/bulletin/an-interdisciplinary-journey-into-consciousness-research-juan-gonzalez.mp3` | `candidate_ready` |

## Corrected Metadata

| Speaker slug | Correction | Rationale |
| --- | --- | --- |
| `brittany_fleig_goldstein` | Display/person name corrected to Brendan Fleig-Goldstein. Slug retained for render-plan compatibility. | Issue03 source `.tex` and `.bib` files list Brendan Fleig-Goldstein, not Brittany. |

## Generated Audio Explicitly Excluded

Local searches find Kokoro/Kokomo generated interview renders for several
remaining speakers under `aliusresearch.org*/site-src/static/media/audio/bulletin/kokoro/`
and `output/audio_interviews/`. These files are complete synthetic audio
transcripts and should not be used as natural voice references for F5 profiles
unless a future audit explicitly confirms that a file contains natural recorded
speech from the named speaker.

## Still Needs Source

| Speaker slug | Display name | Notes / next action |
| --- | --- | --- |
| `alexandra_mikhailova` | Alexandra Mikhailova | No confirmed public voice source found. Checked UC Davis identity pages (`https://lamp-training.ucdavis.edu/people/alexandra-sasha-mikhailova`, `https://grad.neuroscience.ucdavis.edu/training-program-basic-neuroscience-trainees`), SOMA author page (`https://soma.neuroscience.ucdavis.edu/news/update-immigration-visas-dr-falcone`), Active Inference Institute officers page (`https://www.activeinference.institute/officers`), and exact/alias YouTube searches. Avoid skating/fencing, politics, ophthalmology, music, and surname-only hits. Request direct sample or original interview audio. |
| `brittany_fleig_goldstein` | Brendan Fleig-Goldstein | Best current candidate is Cogut Institute exact-name talk `joyEOh8vq9s` (5:31, institutional channel, likely cleaner than the multi-author MathPsych keynote). Verified MathPsych embed `Ez6CnJG9UMY` and exact-name `XD3pYsCexrc` remain fallbacks. Anonymous yt-dlp is blocked by YouTube bot confirmation for all three even with embedded/android/ios extractor clients; retry with exported Netscape cookies or request direct sample. Attempt logs are in `sources/raw/brittany_fleig_goldstein/download_attempt_log.csv`. |
| `cordelia_erickson_davis` | Cordelia Erickson-Davis | No confirmed public voice source found. Checked Stanford profile (`https://med.stanford.edu/profiles/cordelia-erickson-davis`) and dissertation defense event (`https://anthropology.stanford.edu/events/cordelia-erickson-davis-dissertation-defense`); neither exposes public media. Avoid Northampton theatre promo (`https://www.youtube.com/watch?v=TE7JYDDKYNw`) and generic name-noise results. Request direct sample or original interview audio. |
| `jasmine_t_ho` | Jasmine T. Ho | No confirmed public voice source found. Checked PubMed identity record (`https://pubmed.ncbi.nlm.nih.gov/41338124/`) and Frontiers editor page (`https://www.frontiersin.org/research-topics/75729/implementation-and-effectiveness-of-virtual-reality-applications-for-mental-health-assessment-and-intervention`); neither exposes public media. Avoid Jasmine Thompson, Cassey Ho, Jasmine Sandlas, Jasmine Masters, topic-only body-integrity results such as `https://www.youtube.com/watch?v=hLgQwzMSRDs`, and other namesakes. Request direct sample or original interview audio. |
| `jean_remi_martin` | Jean-Remi Martin | No confirmed public voice source found. Checked older ALIUS identity/text pages (`https://www.aliusresearch.org/blog-v1/introducing-jean-remy-martin`, `https://www.aliusresearch.org/blog-v1/jean-remy-martin-consciousness-anaesthetised-placebo-and-metacognition`) and exact/topic YouTube searches; no embedded or downloadable natural-voice media found. Avoid Jean-Remi King, Wyclef/Remy Martin, cognac, performer, priest, and surname-only hits. Request direct sample or original interview audio. |
| `maddalena_canna` | Maddalena Canna | ALIUS Workshop 2018 program confirms her talk, "How to integrate anthropology and neuroscience in a natural context? Proposals for a reflexive bio-social anthropology", in the anthropological perspectives session. Exact ALIUS Workshop YouTube videos `_GkB6Uz-pV0` and `4BAkrF7qhJ4` are currently blocked by YouTube bot confirmation even with embedded/android/ios extractor clients. No better non-YouTube natural-voice source was found in this pass. Retry with exported Netscape cookies, then locate the Canna talk segment before reference extraction. Attempt logs are in `sources/raw/maddalena_canna/download_attempt_log.csv`. |

## Important False Positives

- `juan_gonzalez`: avoid journalist/social-justice Juan Gonzalez, Sabrina Gonzalez/IAI, Cabrini/CUNY/MNN/Democracy Now, ThatWasEpic/LAHWF, and generic meditation channels unless manually verified.
- `maddalena_canna`: avoid cannabis-topic results for "canna" unless explicitly about Maddalena Canna.
- `brittany_fleig_goldstein`: avoid unrelated exact-name personal/non-academic videos unless the institutional Cogut talk and MathPsych keynote are unusable; avoid generic child-content/search-noise results from malformed quoted searches.
- `edvard_aviles`: avoid restaurant, dancer, Ricky/Edward Aviles, St Edward's, Yale, and unrelated generic Aviles content.
- `arnaud_halloy`: avoid `Brasil Fuzue`, `Maracatu Mix`, Arnaud Gallet, Quentin Halloy drums, and unrelated cafe/science results.
