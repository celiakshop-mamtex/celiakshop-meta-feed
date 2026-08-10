# META ads feed — Celiakshop.cz

Doplňuje do Facebook/Meta produktového feedu `g:custom_label_0` s **ABC třídou**
produktu (`a` / `b` / `c`), aby šlo v Meta ads cílit zvlášť na bestsellery.

| Co | Hodnota |
|---|---|
| Zdrojový feed | `https://www.celiakshop.cz/facebook/export/products.xml` |
| Zdroj prodejů | objednávkový CSV export ze Shoptetu (secret `ORDERS_URL`) |
| Výstup | `https://marach1994.github.io/celiakshop-meta-feed/meta-products.xml` |
| Frekvence | denně 04:00 UTC (06:00 letní / 05:00 zimní čas) |
| Kde se mění pravidla | **`rules.yaml`** |

## Jak to funguje

1. Stáhne objednávky za posledních 6 měsíců
2. Seřadí produkty dle tržeb bez DPH, spočítá kumulativní podíl
   → `a` do 80 %, `b` do 95 %, zbytek `c`
3. Stáhne Facebook feed, ke každému produktu podle `g:id` doplní `g:custom_label_0`
4. Publikuje na GitHub Pages

Produkty bez prodeje za 6 měsíců dostanou `c`.

## Lokální spuštění

```bash
pip install -r requirements.txt
export ORDERS_URL="https://www.celiakshop.cz/export/orders.csv?..."
python transform.py
# výsledek: output/meta-products.xml
```

Podrobnosti (co přesně změnit a kde) → **[DOKUMENTACE.md](DOKUMENTACE.md)**
