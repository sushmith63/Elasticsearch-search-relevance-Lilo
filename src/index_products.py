import json
from collections import Counter, defaultdict
from elasticsearch import Elasticsearch, helpers

ES_HOST = "http://127.0.0.1:9200"
INDEX_NAME = "products_v1"

es = Elasticsearch(ES_HOST)

def load_json(path):
    with open(path, "r") as f:
        return json.load(f)

def build_popularity_and_ppu(orders):
    popularity = Counter()
    price_sum = defaultdict(float)
    qty_sum = defaultdict(int)

    for order in orders:
        for item in order.get("cart", {}).get("items", []):
            pid = item.get("product_id")
            qty = int(item.get("quantity", 0) or 0)
            price = item.get("price")

            if not pid:
                continue

            popularity[pid] += qty

            if price is not None and qty > 0:
                price_sum[pid] += float(price)
                qty_sum[pid] += qty

    ppu = {}
    for pid, total_qty in qty_sum.items():
        if total_qty > 0:
            ppu[pid] = price_sum[pid] / total_qty

    return dict(popularity), ppu

def normalize_uom(uom):
    return uom.strip().lower() if isinstance(uom, str) else None

def is_legacy_title(title):
    if not isinstance(title, str):
        return False
    t = title.strip().lower()
    return t in ("legacy sku", "unknown item", "discontinued product")

def product_to_doc(p, popularity_map, ppu_map):
    pid = p.get("_id")
    title = p.get("title")

    return {
        "product_id": pid,
        "sku": p.get("sku"),
        "vendor": p.get("vendor"),
        "title": title,
        "description": p.get("description"),
        "category": p.get("category"),
        "unit_of_measure": normalize_uom(p.get("unit_of_measure")),
        "region_availability": p.get("region_availability", []),
        "supplier_rating": p.get("supplier_rating"),
        "inventory_status": p.get("inventory_status"),
        "bulk_pack_size": p.get("bulk_pack_size"),
        "price_per_unit": ppu_map.get(pid),
        "popularity": popularity_map.get(pid, 0),
        "is_legacy": is_legacy_title(title),
        "attributes": p.get("attributes", {}) or {}
    }

def bulk_index(products, popularity, ppu):
    actions = []
    for p in products:
        doc = product_to_doc(p, popularity, ppu)
        if not doc["product_id"]:
            continue
        actions.append({
            "_index": INDEX_NAME,
            "_id": doc["product_id"],
            "_source": doc
        })
    helpers.bulk(es, actions, request_timeout=120)

if __name__ == "__main__":
    products = load_json("/home/sanju/lilo-assignment/data/products.json")
    orders = load_json("/home/sanju/lilo-assignment/data/orders.json")

    popularity, ppu = build_popularity_and_ppu(orders)
    bulk_index(products, popularity, ppu)

    print("Indexed products:", len(products))
