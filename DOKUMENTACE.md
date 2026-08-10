# Dokumentace — META ads feed pro Celiakshop.cz

> **Účel repozitáře:** doplnit do produktového feedu pro Meta (Facebook) ads značku
> `g:custom_label_0` s **ABC třídou** produktu, aby šlo v kampaních oddělit bestsellery
> od zbytku sortimentu. Běží zdarma na GitHub Actions + GitHub Pages.
>
> Dokument je psaný pro **člověka** (co se s feedem děje, jak něco změnit)
> i pro **LLM / AI asistenta** (přesné mapování pravidlo → kód → konfigurace,
> zdroje pravdy, invarianty). Pokud něco měníš, uprav i tuto dokumentaci.

---

## 1. Rychlý přehled (TL;DR)

| Co | Hodnota |
|---|---|
| Zdrojový feed (vstup) | `https://www.celiakshop.cz/facebook/export/products.xml` |
| Zdroj prodejů | Shoptet CSV export objednávek — env/secret `ORDERS_URL` |
| Formát vstupu i výstupu | RSS 2.0 s namespace `g:` (`base.google.com/ns/1.0`) |
| Počet produktů | ~2 650 |
| Výstupní feed (živý) | `https://marach1994.github.io/celiakshop-meta-feed/meta-products.xml` |
| Frekvence aktualizace | denně v 04:00 UTC (cron v GitHub Actions) |
| Kde se mění pravidla | **`rules.yaml`** |
| Kde je logika | **`transform.py`** (mění se jen zřídka) |

**Princip:** stáhni objednávky → spočítej ABC → stáhni feed → doplň `g:custom_label_0`
→ zapiš `output/meta-products.xml` → publikuj na Pages → Meta si ho stáhne.

---

## 2. Architektura

```
┌──────────────────────┐
│ Shoptet: orders.csv  │──┐
│ (secret ORDERS_URL)  │  │   ┌──────────────┐     ┌───────────────────────┐
└──────────────────────┘  ├──▶│ GitHub       │────▶│ GitHub Pages          │──▶ Meta
┌──────────────────────┐  │   │ Actions      │     │ meta-products.xml     │    Commerce
│ Shoptet: products.xml│──┘   │ transform.py │     │ (veřejná URL)         │    Manager
│ (facebook export)    │      └──────────────┘     └───────────────────────┘
└──────────────────────┘          denně 04:00              výstup
```

Stejné rozhodnutí návrhu jako u ostatních feed repozitářů: **konfigurace odděleně od kódu.**

- **`rules.yaml`** — okno, prahy, mapování tříd na hodnoty labelu. Tady se dělají změny.
- **`transform.py`** — logika. Mění se jen když přibude *nový typ* transformace.

---

## 3. ABC analýza — jak se počítá

Logika je **reprodukcí funkce `calculate_abc_analysis`** ze Streamlit dashboardu
(`C:\Vibecode\report-celiak-new\streamlit\modules\analytics.py`), varianta „Dle tržeb".
Cílem je, aby třída A ve feedu odpovídala tomu, co uživatel vidí na stránce
**3_Produkty → ABC Analýza**.

Postup (funkce `compute_abc` v `transform.py`):

| Krok | Co se děje | Klíč v `rules.yaml` |
|---:|---|---|
| 1 | Filtr na klouzavé okno N měsíců zpět od dne běhu | `abc_window_months` |
| 2 | Vyloučení stornovaných objednávek (`statusName` obsahuje „storno") | `exclude_status_contains` |
| 3 | Vyloučení nezbožových položek (`SHIPPING*`, `BILLING*`) | `exclude_code_prefixes` |
| 4 | Tržba položky = jednotková cena × množství | — |
| 5 | Součet za `orderItemCode`, sestupné řazení | `abc_metric` |
| 6 | Kumulativní podíl → A ≤ 80 %, B ≤ 95 %, zbytek C | `abc_threshold_a`, `abc_threshold_b` |

**Jednotková cena:** pokud je vyplněná `orderItemUnitDiscountPriceWithoutVat`, použije se ona
(i když je 0 = položka zdarma), jinak `orderItemUnitPriceWithoutVat`. Přesně jako `_item_revenue`
v dashboardu.

### Invarianty (DŮLEŽITÉ pro správné úpravy)

1. **Kupóny (`COUPON*`) se NEVYLUČUJÍ.** Dashboard je taky nevylučuje — jeho `_exclude_shipping`
   filtruje jen `SHIPPING` a `BILLING`. Kupóny mají zápornou tržbu (−33 tis. Kč / 6 měsíců),
   takže snižují celkový součet a hranice A je o něco přísnější.
   Ověřeno: se současným nastavením vychází **473 produktů ve třídě A, 0 rozdílů proti dashboardu**.
   Kdyby se `COUPON` do `exclude_code_prefixes` přidal, třída A se rozšíří (naposledy o 17 produktů)
   a **přestane sedět na dashboard**.
2. **Napojení feedu na prodeje je přes `g:id` = `orderItemCode`.** Kódy sedí přímo, žádná mapovací
   tabulka není potřeba (ověřeno: 2 129 z 2 646 produktů feedu má záznam v objednávkách).
3. **Produkty bez prodeje v okně** (ve feedu jsou, v objednávkách ne — naposledy 1 019 kusů)
   dostanou třídu z `unsold_class`. Prázdná hodnota = element nedostanou vůbec.
4. **Feed se jinak nemění.** Přidá se výhradně `g:custom_label_0`; ověřeno porovnáním struktury
   všech 2 646 produktů proti zdroji — 0 jiných změn.
5. **CDATA se ve výstupu rozbalí na escapované entity.** ElementTree CDATA nezachovává.
   Je to validní XML se stejným obsahem, Meta i Google to čtou bez problému (stejné chování
   mají i ostatní feed repozitáře).

---

## 4. Jak co změnit (cookbook)

Skoro všechny běžné úpravy = editace `rules.yaml`. Po commitu a pushi se změna projeví
při dalším běhu (nebo hned přes Actions → Run workflow).

### ➤ Změnit období pro ABC
```yaml
abc_window_months: 12   # místo 6
```

### ➤ Počítat ABC podle marže místo tržeb
```yaml
abc_metric: "margin"
```
Marže = tržba − (nákupní cena bez DPH × množství). Nákupní cena je v Shoptetu **s DPH**,
skript ji dělí `(1 + sazba/100)`.

> Pozn.: dashboard má u marže ještě fallback na nákupní cenu z produktového feedu, když
> ji objednávka nemá. Tady fallback není (produktový CSV feed se nestahuje), takže
> u položek bez nákupní ceny vyjde marže = celá tržba. Pro `abc_metric: revenue` se to neuplatní.

### ➤ Posunout hranici třídy A
```yaml
abc_threshold_a: 0.70   # A = kumulativně do 70 % tržeb
```

### ➤ Označovat jen třídu A (bez b/c)
```yaml
labels:
  A: "a"
  B: ""
  C: ""
unsold_class: ""
```

### ➤ Psát do jiného custom labelu
```yaml
label_element: "custom_label_2"
```

### ➤ Změnit hodnoty labelu
```yaml
labels:
  A: "bestseller"
  B: "standard"
  C: "long-tail"
```

### ➤ Změnit frekvenci aktualizace
V `.github/workflows/transform-feed.yml`, řádek `cron:` (čas je v UTC).

---

## 5. Referenční popis `rules.yaml`

| Klíč | Typ | Význam |
|---|---|---|
| `feed_url` | string | URL zdrojového Facebook feedu |
| `output_file` | string | Název výstupního souboru v `output/` |
| `abc_window_months` | int | Kolik měsíců zpět se počítají tržby |
| `abc_metric` | string | `revenue` nebo `margin` |
| `abc_threshold_a` | float | Kumulativní podíl pro třídu A (0.80) |
| `abc_threshold_b` | float | Kumulativní podíl pro třídu B (0.95) |
| `unsold_class` | string | Třída pro produkty bez prodeje; prázdné = bez labelu |
| `label_element` | string | Do kterého elementu se zapisuje (`custom_label_0`) |
| `labels` | mapa | Třída (A/B/C) → hodnota zapsaná do feedu |
| `exclude_status_contains` | string | Text ve `statusName` označující storno |
| `exclude_code_prefixes` | seznam | Prefixy nezbožových položek objednávky |

---

## 6. Ověřování správnosti

Klasifikace byla ověřena proti dashboardu — přímým zavoláním `calculate_abc_analysis`
nad stejnými objednávkami a stejným oknem:

```
dashboard A: 473 | transform A: 473 | shoda: 473 | rozdíl: 0
```

**Jak ověření zopakovat:**

```python
import sys, os, yaml, pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
sys.path.insert(0, r'C:\Vibecode\report-celiak-new\streamlit')
import transform
from modules.analytics import calculate_abc_analysis

orders = transform.load_orders(os.environ['ORDERS_URL'])
products = pd.read_csv('.../data/cache/products_YYYYMMDD.csv', sep=';', encoding='utf-8-sig')
date_to = datetime.now(); date_from = date_to - relativedelta(months=6)
dash = calculate_abc_analysis(orders, products, date_from, date_to)
dash_a = set(dash[dash['abc_class'] == 'A']['product_code'])
mine_a = {k for k, v in transform.compute_abc(orders, yaml.safe_load(open('rules.yaml', encoding='utf-8'))).items() if v == 'A'}
print(len(dash_a), len(mine_a), len(dash_a ^ mine_a))
```

Kontrola výstupu feedu (počty labelů):
```bash
python -c "import xml.etree.ElementTree as ET,collections;G='{http://base.google.com/ns/1.0}';i=ET.parse('output/meta-products.xml').getroot().find('channel').findall('item');print(collections.Counter(x.findtext(G+'custom_label_0') for x in i))"
```

---

## 7. Nastavení na GitHubu (jednorázově)

1. **Secret:** Settings → Secrets and variables → Actions → New repository secret
   - Název: `ORDERS_URL`
   - Hodnota: Shoptet export objednávek (`https://www.celiakshop.cz/export/orders.csv?patternId=67&dateFrom=2024-1-1&partnerId=3&hash=…`)
   - Stejná hodnota je v `report-celiak-new/streamlit/.streamlit/secrets.toml`
2. **Pages:** Settings → Pages → Source: **GitHub Actions**
3. **První běh:** Actions → „Transform META Feed (Celiakshop.cz)" → Run workflow
4. **Meta Commerce Manager:** katalog → zdroje dat → naplánované načítání z URL výstupu

> Pozn.: po úplně prvním pushi se workflow nemusí hned zaregistrovat. Pomůže prázdný
> commit / drobná změna workflow souboru a push znovu.

---

## 8. Známá omezení

- **Okno se posouvá každý den**, takže produkty na hranici A/B mohou třídu měnit ze dne na den.
  Při 6měsíčním okně je to spíš výjimka, ale u kampaní filtrovaných na `custom_label_0 = a`
  s tím počítej. Delší okno (`abc_window_months: 12`) kolísání sníží.
- **Kategorie produktu se do ABC nepromítá** — klasifikace je vždy přes celý sortiment,
  ne v rámci kategorie (stejně jako dashboard bez zapnutého filtru kategorií).
- **`ORDERS_URL` obsahuje hash** — je to citlivý údaj, patří výhradně do GitHub secrets,
  nikdy ne do `rules.yaml` ani do commitu.

---

## 9. Mapa souborů

```
celiakshop-meta-feed/
├── transform.py                      # logika: ABC výpočet + zápis do feedu
├── rules.yaml                        # konfigurace ← tady se edituje
├── requirements.txt                  # requests, PyYAML, pandas
├── README.md                         # stručný přehled
├── DOKUMENTACE.md                    # tento soubor
├── .gitignore                        # ignoruje output/, __pycache__, .env
├── .github/workflows/
│   └── transform-feed.yml            # denní cron + build + deploy na Pages
└── output/                           # (generováno, negitováno) meta-products.xml
```

---

## 10. Vztah k ostatním feed repozitářům

Stejný vzor (transform.py + rules.yaml → Actions → Pages) používají:

| Repo | Účel |
|---|---|
| `chemie-bazen-google-merchant-feed` | Google Nákupy CZ, náhrada Mergada 224446 |
| `mamtex-feed` | Google Shopping, náhrada Mergada 22970 |
| `celiakshop-sk-feedy` | Google Merchant SK |
| `celiakshop-meta-feed` | **tento repo** — Meta ads + ABC labely |

Odlišnost tohoto repa: potřebuje **secret** (`ORDERS_URL`) a **druhý datový zdroj**
(objednávky), ostatní jen transformují jeden vstupní feed.
