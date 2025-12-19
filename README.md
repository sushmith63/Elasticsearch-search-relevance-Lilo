# Lilo Elasticsearch

This repository contains a local Elasticsearch setup and relevance experiments for a B2B-style product catalog.

## Structure
- `/src` – ingestion scripts
- `/data` – provided datasets
- `/docs` – report and query examples
- `mapping.json` - index settings and analyzers

## How to Run
1. Start Elasticsearch locally
2. Create index using `mapping.json`
3. Run `src/index_products.py` to index data
4. Execute query examples in `/docs/queries`
5. See relevance analysis in `/docs/report.md`
