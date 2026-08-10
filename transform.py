#!/usr/bin/env python3
"""META ads feed pro celiakshop.cz — doplní g:custom_label_0 = ABC třída.

ABC klasifikace reprodukuje logiku Streamlit dashboardu
(streamlit/modules/analytics.py → calculate_abc_analysis, varianta „Dle tržeb"):
produkty se seřadí sestupně dle tržeb bez DPH za klouzavé okno, spočítá se
kumulativní podíl na celkových tržbách a podle prahů se přiřadí A / B / C.

Zdroj prodejů: objednávkový CSV export ze Shoptetu (env ORDERS_URL).
Zdroj produktů: Facebook XML feed z e-shopu (rules.yaml → feed_url).
"""

import io
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd
import requests
import yaml
from dateutil.relativedelta import relativedelta

G_NS = "http://base.google.com/ns/1.0"
ET.register_namespace("g", G_NS)

# Sloupce objednávkového exportu, které potřebujeme jako čísla
NUMERIC_COLS = [
    "orderItemAmount",
    "orderItemUnitPriceWithoutVat",
    "orderItemUnitDiscountPriceWithoutVat",
    "orderItemUnitPriceVatRate",
    "orderItemUnitPurchasePrice",
]


def g(tag):
    return f"{{{G_NS}}}{tag}"


def set_or_create(item, tag, value):
    """Vytvoří element (pokud chybí) a nastaví text."""
    el = item.find(tag)
    if el is None:
        el = ET.SubElement(item, tag)
    el.text = value
    return el


def load_orders(url):
    """Stáhne a naparsuje objednávkový CSV export (cp1250, oddělovač ;)."""
    try:
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"Chyba stahování objednávek: {e}")
    print(f"Objednávky staženy: {len(resp.content) / 1024 / 1024:.1f} MB")

    df = pd.read_csv(io.BytesIO(resp.content), sep=";", encoding="cp1250")
    df.columns = df.columns.str.strip()

    if "date" not in df.columns or "orderItemCode" not in df.columns:
        sys.exit("Objednávkový export nemá očekávané sloupce (date, orderItemCode)")

    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    df["orderItemCode"] = df["orderItemCode"].astype(str).str.strip()
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.replace(",", ".", regex=False)
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_abc(df, rules):
    """Vrátí dict {kód produktu: "A"|"B"|"C"} podle prodejů v klouzavém okně."""
    months = int(rules.get("abc_window_months", 6))
    date_to = pd.Timestamp(datetime.now())
    date_from = pd.Timestamp(datetime.now() - relativedelta(months=months))
    df = df[(df["date"] >= date_from) & (df["date"] <= date_to)]
    print(f"Okno ABC: {date_from:%d.%m.%Y} – {date_to:%d.%m.%Y} ({months} měs.)")

    # Stornované objednávky ven
    status_kw = (rules.get("exclude_status_contains") or "").strip().lower()
    if status_kw and "statusName" in df.columns:
        mask = df["statusName"].astype(str).str.lower().str.contains(status_kw, na=False)
        df = df[~mask]

    # Doprava, platba, kupóny ven
    prefixes = tuple(rules.get("exclude_code_prefixes") or [])
    if prefixes:
        df = df[~df["orderItemCode"].str.startswith(prefixes, na=False)]

    if df.empty:
        sys.exit("V okně nejsou žádné objednávky — ABC nelze spočítat")

    # Tržba položky: sleva má přednost, i když je 0 (položka zdarma) — jako v dashboardu
    discount = df["orderItemUnitDiscountPriceWithoutVat"]
    unit_price = discount.where(discount.notna(), df["orderItemUnitPriceWithoutVat"])
    amount = df["orderItemAmount"].fillna(0)
    revenue = unit_price.fillna(0) * amount

    metric = (rules.get("abc_metric") or "revenue").strip().lower()
    if metric == "margin":
        # Nákupní cena je v Shoptetu S DPH → převod na bez DPH kvůli shodné základně
        vat_rate = df["orderItemUnitPriceVatRate"].fillna(0)
        unit_cost = (df["orderItemUnitPurchasePrice"] / (1 + vat_rate / 100)).fillna(0)
        value = revenue - unit_cost * amount
    elif metric == "revenue":
        value = revenue
    else:
        sys.exit(f"Neznámá hodnota abc_metric: {metric!r} (povoleno: revenue, margin)")

    agg = (
        df.assign(_value=value)
        .groupby("orderItemCode", as_index=False)["_value"]
        .sum()
        .sort_values("_value", ascending=False)
        .reset_index(drop=True)
    )

    total = agg["_value"].sum()
    if total <= 0:
        sys.exit(f"Součet metriky {metric} je {total} — ABC nelze spočítat")

    threshold_a = float(rules.get("abc_threshold_a", 0.80))
    threshold_b = float(rules.get("abc_threshold_b", 0.95))
    cumulative = agg["_value"].cumsum() / total

    classes = {}
    for code, cum in zip(agg["orderItemCode"], cumulative):
        if cum <= threshold_a:
            classes[code] = "A"
        elif cum <= threshold_b:
            classes[code] = "B"
        else:
            classes[code] = "C"

    counts = {c: sum(1 for v in classes.values() if v == c) for c in ("A", "B", "C")}
    print(
        f"ABC dle metriky '{metric}': "
        f"A={counts['A']}, B={counts['B']}, C={counts['C']} "
        f"(celkem {len(classes)} prodávaných kódů)"
    )
    return classes


def main():
    with open("rules.yaml", encoding="utf-8") as f:
        rules = yaml.safe_load(f)

    orders_url = os.getenv("ORDERS_URL", "").strip()
    if not orders_url:
        sys.exit("Chybí proměnná ORDERS_URL (GitHub secret / .env)")

    classes = compute_abc(load_orders(orders_url), rules)

    feed_url = rules["feed_url"]
    print(f"Stahování feedu: {feed_url}")
    try:
        resp = requests.get(feed_url, timeout=300)
        resp.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"Chyba stahování feedu: {e}")
    print(f"Staženo: {len(resp.content) / 1024:.0f} KB")

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError as e:
        sys.exit(f"Chyba parsování XML: {e}")

    channel = root.find("channel")
    if channel is None:
        sys.exit("XML neobsahuje element <channel>")

    items = channel.findall("item")
    print(f"Nalezeno produktů: {len(items)}")

    labels = rules.get("labels") or {}
    label_element = rules.get("label_element", "custom_label_0")
    unsold_class = (rules.get("unsold_class") or "").strip().upper()

    written = {"A": 0, "B": 0, "C": 0}
    unsold = 0

    for item in items:
        pid = (item.findtext(g("id")) or "").strip()
        cls = classes.get(pid)
        if cls is None:
            unsold += 1
            cls = unsold_class or None
        if not cls:
            continue
        label = labels.get(cls)
        if label:
            set_or_create(item, g(label_element), str(label))
            written[cls] = written.get(cls, 0) + 1

    print(
        f"Zapsáno {label_element}: "
        f"a={written['A']}, b={written['B']}, c={written['C']} "
        f"| bez prodeje v okně: {unsold}"
    )
    if written["A"] == 0:
        print("VAROVÁNÍ: žádný produkt ve feedu nedostal třídu A — zkontroluj kódy produktů")

    os.makedirs("output", exist_ok=True)
    out_path = os.path.join("output", rules.get("output_file", "meta-products.xml"))
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(out_path, xml_declaration=True, encoding="unicode")

    size_kb = os.path.getsize(out_path) / 1024
    print(f"Zapsáno: {out_path} ({size_kb:.0f} KB, {len(items)} produktů)")


if __name__ == "__main__":
    main()
