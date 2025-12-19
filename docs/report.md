# Lilo Elasticsearch – Search & Relevance Notes

## 1) Setup & Data Ingestion

- Elasticsearch running locally on Ubuntu VM (single node).
- Created index `products_v1` using a custom mapping + analyzer (lowercasing + synonym filter).
- Indexed 10,000 products via `src/index_products.py` (bulk indexing).
- Verified ingestion:
  - `GET products_v1/_count` returned `10000`.

---

## 2) Baseline Search Queries (Q1–Q5)

I started with a baseline `multi_match` query across:
- `title` (highest weight)
- `description`
- `category.text`

This produced valid results but showed noisy relevance due to the dataset containing cross-contaminated tokens (e.g., “tomato color”, “hp”, “bulk pack”, “PVC” appearing across unrelated categories).

### Example baseline issue
For query **Q1: “3 hp sewage pump weir”**, top matches included categories such as:
- Makeup / Cosmetics
- Gloves
- Lubricants

This suggests the text fields contain overlapping keywords and synonyms that are not aligned to true intent.

---

## 3) Relevance Improvement – Technical Query Guardrails (Fix 1)

### Attempt 1 (too strict)
I first tried a strict technical template using:
- `operator: "and"` (all terms must match)
- exclusion filters for unrelated categories (Makeup/Cosmetics)

Result: **0 hits** for Q1/Q2/Q3 (over-filtering due to noisy/partial text fields).

### Fix 1 v2
I relaxed the strict query by:
- using `operator: "or"`
- applying `minimum_should_match` to require partial term overlap
- boosting title matches
- keeping category exclusions (Makeup/Cosmetics) as a guardrail

This improved results substantially while still preventing obvious intent mismatch.

### Data Quality Handling: Synonyms & Fuzzy Matching

To improve robustness against noisy and inconsistent catalog data, synonyms are applied at **analysis time** using a custom Elasticsearch synonym filter (`lilo_synonyms`). This ensures common B2B term variations (e.g., hp ↔ horsepower, mm ↔ millimeter) are normalized consistently during both indexing and querying. In addition, fuzzy matching (`fuzziness: AUTO`) is enabled in multi-field keyword queries to tolerate typos, misspellings, and incomplete terms commonly found in user-entered search queries.


**Observed results after Fix 1 v2:**
- Q1 strict v2 total hits: **435**
- Q2 strict v2 total hits: **195**
- Q3 strict v2 total hits: **4772**
- Top results no longer included Makeup/Cosmetics categories for technical queries.

---

## 4) Intent-Aware Category Boosting for “Tomato” Queries (Fix 2)

Because “tomato” can represent multiple intents (Food vs Makeup shade names), I used `function_score` to boost expected category prefixes:

- For **Q4: “tomato”**, boosted `Food*` and downweighted `Tools*`.
- For **Q5: “tomato makeup”**, boosted `Makeup*` and downweighted `Tools*` / `Industrial*`.

This approach demonstrates intent-aware ranking without requiring ML models.

---

## 5) Persona-Based Ranking (Task 4)

I implemented two personas for the same query (**“nitrile gloves bulk pack”**):

### Persona A: Heavy Buyer
Goal: prefer popular, reputable, available products.

Signals:
- `popularity` (sqrt factor)
- `supplier_rating`
- `inventory_status == in_stock`

### Persona B: Budget Buyer
Goal: prefer cheaper unit pricing while maintaining basic quality.

Signals:
- `price_per_unit` using reciprocal scoring (lower price → higher score)
- `supplier_rating`
- Added `exists(price_per_unit)` filter to ensure pricing-based scoring is meaningful

### observation
Due to noisy catalog data and cross-domain categories, purely “cheapest” scoring can surface irrelevant items (e.g., food categories with extremely low `price_per_unit`) unless persona scoring is applied within strong intent constraints (category filtering or learned intent classification).

### Before vs After Persona-Based Ranking

In the baseline search configuration, all users receive the same ranking driven primarily by textual relevance across product title, description, and attributes. After introducing persona-based boosting, ranking behavior changes by user context: a heavy enterprise buyer query boosts products with higher historical popularity and supplier reliability, while a budget-focused buyer query boosts products with lower `price_per_unit`. As a result, identical queries can return different top-ranked products aligned with each persona’s purchasing priorities.


In a production system, I would:
- detect intent first (category prediction / query classification),
- then apply persona scoring only within that intent domain.

---

## 6) Improvements

I would prioritize:

1. **Query intent classification**
   - lightweight rules initially (keyword triggers),
   - upgrade to learned classifier using click logs.

2. **Better category normalization**
   - standardize category taxonomy (typos like “Grinderz”, inconsistent paths, etc.).
   - consider mapping to canonical categories and searching on normalized fields.

3. **Field cleanup**
   - reduce impact of noisy descriptions with separate analyzed fields (e.g., `description_clean`).
   - index structured fields (hp, diameter, units) separately for precision filters.

4. **Synonyms management**
   - use curated synonyms per-category instead of global synonyms (to avoid cross-domain drift).

5. **Learning-to-rank / vector reranking**
   - once click/purchase feedback exists, consider LTR or hybrid vector+BM25 reranking.

6. **Unit normalization and deduplication**
   - Normalize numeric attributes at ingestion time (e.g., converting kg/lb/oz to grams and mm/cm/in to millimeters) to enable consistent filtering, sorting, and scoring.
   - Detect near-duplicate products using normalized titles, vendor identifiers, and attribute similarity, collapsing or merging duplicates to prevent result pollution and improve relevance.

---

## 7) Files Produced

- Query JSON files in: `queries/`
- Result outputs in: `results/`
- Technical guardrail queries:
  - `template_technical_v2.json`
  - `q1_*_strict_v2.json`, `q2_*_strict_v2.json`, `q3_*_strict_v2.json`
- Persona queries:
  - `persona_heavy_buyer_v2.json`
  - `persona_budget_buyer_v2.json`

## 8) Limitations

This solution intentionally focuses on relevance reasoning rather than full production hardening. With the following risks and trade-offs:

### 1. Cross-Domain Synonym Risk
Using global synonyms (e.g., “tomato color”, “bulk pack”, “hp”) can introduce cross-category relevance drift, where unrelated domains (Food, Makeup, Industrial) influence each other.

**Mitigation:**
- Prefer category-scoped synonym sets in production.
- Apply synonyms selectively to technical fields rather than free-text descriptions.

---

### 2. Over-Filtering Risk (False Negatives)
Strict technical queries using `operator: and` and hard category exclusions initially resulted in zero hits due to noisy and incomplete text fields.

**Mitigation:**
- Use `minimum_should_match` instead of strict AND logic.
- Apply exclusions as soft guardrails rather than absolute filters.

---

### 3. Intent Misclassification Risk
Rule-based intent handling (e.g., boosting Food vs Makeup for “tomato”) may fail for ambiguous or long-tail queries.

**Mitigation:**
- Start with keyword-based intent rules.
- Gradually introduce learned intent classifiers using click or purchase logs.

---

### 4. Persona Scoring Leakage
Persona-based scoring (e.g., cheapest-wins for Budget Buyer) can surface irrelevant products if applied globally across all categories.

**Mitigation:**
- Apply persona scoring only after intent/category narrowing.
- Combine persona scoring with minimum relevance thresholds.

---

### 5. Popularity Bias
Boosting popularity can reinforce feedback loops where already popular products dominate results, reducing discovery.

**Mitigation:**
- Apply diminishing returns (e.g., sqrt or log scaling).
- Balance popularity with freshness or diversity signals.

---

### 6. Data Quality Dependency
Relevance quality is highly dependent on data cleanliness (category consistency, structured fields, unit normalization).

**Mitigation:**
- Normalize categories into canonical taxonomies.
- Extract structured attributes (hp, diameter, units) into dedicated fields.

---

### 7. Scalability Considerations
This implementation uses a single-node Elasticsearch setup and query-time scoring logic.

**Mitigation:**
- In production, evaluate shard sizing, caching strategies, and offline feature computation.
- Move complex scoring logic to reranking layers if query latency becomes an issue.

## Use of Orders Data

The provided `orders.json` dataset represents transactional purchase data.

In this implementation, orders data was **used indirectly** to derive
catalog-level ranking signals such as:

- Product popularity
- Price-per-unit (PPU) for bulk purchasing comparisons

These derived signals were computed offline during ingestion and stored
directly on product documents. They were then used for persona-based
ranking and relevance tuning.

Raw orders data (e.g., per-user history, recency-weighted demand, or
session-based personalization) was intentionally not queried at search
time, as the scope of this exercise focused on catalog relevance, index
design, and deterministic ranking strategies.

In a production system, orders data would additionally be leveraged for:
- Learning-to-rank (LTR) training
- Personalized recommendations
- Recency-aware demand boosts
- User-specific re-ranking

This approach mirrors common production patterns where behavioral data
is transformed into stable ranking features rather than queried
directly in real time.


