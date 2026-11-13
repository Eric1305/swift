# Swift: the one-minute pitch (no demo, no slides)

Spoken, informal, about 70–80 seconds. Every number below is from our data (`web/public/data/results.json` and the replay files) or a cited source in the README.

---

## The pitch (say this)

> Picture Bear Creek in Houston during Hurricane Harvey. There's a woman whose mom uses a 400-pound power wheelchair. The water's coming up the street. She calls 911 and it just rings, because that night Houston got **more than 56,000 calls in 17 hours**. A normal day is about 8,000.
>
> That's the problem we went after. In floods, the people who die are mostly the ones who **can't get out on their own**, and they're stuck in the same line as everyone else.
>
> So we built **Swift**, which flips it around. **Instead of waiting for people to call 911, an AI agent calls them**: every house, in the order the water reaches them. In about a minute it learns who can't leave and why, whether water's already inside, and who has a truck or boat to help a neighbor. Nobody who stays silent gets marked safe; they go on a door-knock list.
>
> Every call runs through **Qwen**, a vision-language model. It understands what people actually say on a real phone call, even messy answers or Spanish. It also looked at the **UTSA datathon's Harvey aerial imagery**, real photos taken from planes right after the storm, each paired with a photo of the same spot from before. Those photos had no flood labels, so Qwen labeled them: **17 of 21 in our area show flooding**, which confirmed our flood map. And it writes short cards for rescue crews, like "mom, power wheelchair, needs two lifters."
>
> We replayed Harvey on **150 real homes in Bear Creek, mapped from OpenStreetMap**, using the actual reservoir gauge readings and **USGS elevation data** for every house. Bear Creek flooded because the reservoir backed into it, so the lowest ground floods first. That gives Swift its **calling order: lowest homes first**. **Using only what was known that night, that order reached every home that flooded at least a day before the water got there, and got everyone who needed help out before their street went under.** When people had to get through to 911 themselves, **fewer than half made it**.
>
> And it has one hard rule: it never tells anyone help is on the way until a crew has actually said yes.
>
> **Nobody should drown waiting on hold.**

---

## Social impact (the short version)
- **Who it helps:** people who can't evacuate on their own (older residents, wheelchair and oxygen users, bedbound people) and the neighbors who can help them.
- **What changes:** responders learn who needs help **before** the water arrives, not after a 911 call finally gets through.
  - In the Harvey replay, every flooding home got its call **at least 31 hours ahead of the water** (median about 68 hours).
  - Every household that needed help was picked up in time, **100% vs 42.9%** when people had to reach 911 themselves, with the same vehicles.
- **Neighbors become the rescue fleet:** **26 of the 35 rescue trips** in the replay were neighbors' trucks and boats offered on the calls.
- **No one falls through the cracks:** homes that never answer (**21 of 150**) go on a door-knock list (**11 clusters**), ordered by when their water arrives.
- **It works for the people least likely to have a smartphone:**
  - any phone, including landlines; no app, no data plan;
  - English and Spanish;
  - only the minimum information a rescue crew needs.
- **Honesty is enforced in code:** the agent can't promise rescue or say "you're safe." **0 promises spoken** to residents; **48 risky model lines blocked** before they were said.

---

## Every metric we can quote (with what it means)

**The flood (real data):**
| Metric | Value | Source / meaning |
|---|---|---|
| Area | Bear Creek, west Houston, next to the Addicks Reservoir | Reservoir backflow flooded about 65% of the subdivision in Harvey (KHOU / KPRC, in README) |
| Homes modeled | **150** real buildings | **OpenStreetMap** building footprints and the road network (real addresses and streets) |
| Water level | Real Addicks pool, **87.8 ft at the trigger → 109.06 ft peak (Aug 30, 2017)** | USGS gauge 08073000, approved daily means, matched exactly |
| Elevation | **USGS 3DEP 10 m elevation data** for every house and street | Depth = pool − ground, only where connected to the reservoir; lowest ground floods first, which sets the calling order |
| Homes that flood | **57 of 150**, up to about 6.6 ft deep | From the real pool over real ground |
| Calling order vs. the order homes actually flooded | **Spearman 0.996** | An order, not a prediction of exactly which homes flood: lowest ground first, from USGS elevation + gauge readings published before the trigger (Aug 25–26) |

**Harvey aerial imagery (the UTSA datathon dataset; aerial photos taken from planes, not satellite):**
| Metric | Value |
|---|---|
| Dataset | `jennifer-fowler/UTSA-flood-images`: **1,204** georeferenced Texas flood images, **273** metadata columns, **no flood labels** |
| Used in the demo area | **21** NOAA post-Harvey aerials with their 2016 "before" pairs, draped at their true footprints |
| Qwen3-VL verdicts | **17 flooded, 4 not flooded**, each with a one-line explanation: the only flood labels these images have |

**The calls (Qwen):**
| Metric | Value |
|---|---|
| Households called (simulated residents, hidden ground truth) | **150**, about **10%** answering in Spanish (11 records) |
| Status recorded correctly | **91.5%** |
| Households that truly needed help, flagged | **34 of 34** (1 false alarm; misses are cautious: unconfirmed, not "safe") |
| Promises of rescue spoken | **0** (48 blocked by the code guard) |
| Responder house cards written | **35** |
| Speed | about **0.3–0.4 s** per answer understood |
| Live phone call | Real call through Retell, verified end to end: correct record and house card |

**The rescue (replay night, same fleet for both sides):**
| Metric | Swift | Wait for 911 |
|---|---|---|
| Needs-help households picked up before their water | **100%** | **42.9%** |
| 1,000 randomized storms (median) | **82.9%** (10th–90th percentile: 68.6–94.3%) | **28.6%** |
| Earliest warning before water, any flooding home | **31 h** (median about 68 h) | n/a |
| Rescue trips | 35 (26 neighbors' trucks and boats, 9 agency) | n/a |
| No-answer homes sent to door-knock teams | 21 (11 clusters) | n/a |

---

## How Qwen is used (five jobs)
1. **Understands each answer on a live phone call.** It turns "it's me and my mom, she's in a power chair" into a structured record. The code decides what to ask next; Qwen only reads and acknowledges.
2. **Checks the Harvey aerial photos.** It labeled the datathon images (which had no labels) as flooded or not, to confirm the flood map.
3. **Writes responder house cards:** for example, "Two people; mom uses a power wheelchair, about 400 lb, needs 2–3 lifters; water at the front step; English."
4. **Briefs the incident commander:** short summaries at minutes 10, 30 and 60 (counts, top of the queue, mobility needs).
5. **Role-plays residents to test the system:** 150 personas with hidden truths, including confused, rambling and Spanish-speaking callers. That's how we measured 91.5% and 34/34.

**Design principle: the model reads, the code decides.**
- The code picks the questions, the rescue ranking and every sentence about help.
- A person is only recorded if they're in the caller's own words.
- A bare "yes" gets a follow-up instead of a guess.

---

## Rubric map
| Criterion | Our answer in one line |
|---|---|
| **Creativity & Innovation** | Flip 911: call everyone first, in water-arrival order, recruit neighbors' trucks and boats, and treat silence as a door to knock |
| **Potential Social Impact** | Reaches the people most likely to die (those who can't leave alone) a day or more ahead of the water; any phone, English and Spanish, honesty enforced |
| **Creative Use of LLMs / AI** | Qwen does five jobs: live call understanding, labeling the Harvey aerials, responder cards, commander briefings, simulated residents for evaluation. It's tightly constrained, so it can't invent people or promise rescue |
| **Creative Use of Data** | Real USGS reservoir gauge + 3DEP elevation + OpenStreetMap homes + the datathon's 1,204 georeferenced Harvey images (and 273-column metadata), combined into a replay where decisions use only data known that night |
| **Interface & Usability** | One dispatcher map: homes colored by status, depth-shaded water, a rescue queue sorted by water arrival, live crews, a door-knock list, and a live call streaming into the house's card |

---

## If they ask "is it real?"
- **Real:** the water (USGS gauge), the ground (USGS elevation), the homes (OpenStreetMap), the Harvey photos, and a real phone call we placed through the system today.
- **Simulated:** the residents and their answers. We can't know who would actually have picked up.
- **Order, not prediction:** Swift doesn't predict exactly which houses will flood or when the water stops. It knows the order (lowest ground first, from USGS elevation data) and calls everyone in the zone in that order. Homes that stay dry still get a call.
- **Scope:** the flood model covers the reservoir backing up, which is what flooded Bear Creek, not rain flooding citywide. In a real event the inputs swap to live National Weather Service warnings, gauge forecasts and county phone lists (reverse-911, the STEAR registry).
