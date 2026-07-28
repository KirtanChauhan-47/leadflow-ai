"""Simple, explainable duplicate detection.

A lead is flagged as a probable duplicate if, compared to another lead:
    1. normalized email is the same, or
    2. normalized phone is the same, or
    3. normalized name and normalized company are the same.

As a small bonus, RapidFuzz is used to catch the same person typed with a
slightly different name at the same company (e.g. "Jon Smith" vs
"John Smith"). This stays optional and lightweight on purpose.
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd
from rapidfuzz import fuzz

from backend.cleaning import clean_text

FUZZY_NAME_THRESHOLD = 90

REASON_EMAIL = "Same normalized email"
REASON_PHONE = "Same normalized phone"
REASON_NAME_COMPANY = "Same normalized name and company"
REASON_FUZZY_NAME = "Similar name and same company (fuzzy match)"
REASON_LINKED = "Matches another record in this duplicate group"


def normalize_name(name) -> Optional[str]:
    text = clean_text(name)
    if not text:
        return None
    return text.lower()


class _UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[rj] = ri


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with is_duplicate / duplicate_group /
    duplicate_reason columns populated."""
    df = df.reset_index(drop=True)
    n = len(df)
    if n == 0:
        df["is_duplicate"] = []
        df["duplicate_group"] = []
        df["duplicate_reason"] = []
        return df

    uf = _UnionFind(n)
    reasons: List[set] = [set() for _ in range(n)]

    email_map: Dict[str, int] = {}
    phone_map: Dict[str, int] = {}
    namecomp_map: Dict[Tuple[str, str], int] = {}

    norm_names = [normalize_name(name) for name in df["name"]]

    for i in range(n):
        email = df.at[i, "email"]
        phone = df.at[i, "phone"]
        norm_name = norm_names[i]
        norm_company = df.at[i, "normalized_company"]

        if email:
            if email in email_map:
                j = email_map[email]
                uf.union(i, j)
                reasons[i].add(REASON_EMAIL)
                reasons[j].add(REASON_EMAIL)
            else:
                email_map[email] = i

        if phone:
            if phone in phone_map:
                j = phone_map[phone]
                uf.union(i, j)
                reasons[i].add(REASON_PHONE)
                reasons[j].add(REASON_PHONE)
            else:
                phone_map[phone] = i

        if norm_name and norm_company:
            key = (norm_name, norm_company)
            if key in namecomp_map:
                j = namecomp_map[key]
                uf.union(i, j)
                reasons[i].add(REASON_NAME_COMPANY)
                reasons[j].add(REASON_NAME_COMPANY)
            else:
                namecomp_map[key] = i

    # Lightweight fuzzy pass: same normalized company, similar (not
    # identical) names. O(k^2) within each company bucket only.
    company_buckets: Dict[str, List[int]] = {}
    for i in range(n):
        company = df.at[i, "normalized_company"]
        if company:
            company_buckets.setdefault(company, []).append(i)

    for indices in company_buckets.values():
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                i, j = indices[a], indices[b]
                name_i, name_j = norm_names[i], norm_names[j]
                if not name_i or not name_j or name_i == name_j:
                    continue
                similarity = fuzz.token_sort_ratio(name_i, name_j)
                if similarity >= FUZZY_NAME_THRESHOLD:
                    uf.union(i, j)
                    reasons[i].add(REASON_FUZZY_NAME)
                    reasons[j].add(REASON_FUZZY_NAME)

    groups: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    is_duplicate = [False] * n
    duplicate_group = [None] * n
    duplicate_reason = [None] * n

    group_counter = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue
        group_counter += 1
        group_id = f"DUP-{group_counter:03d}"
        for idx in members:
            is_duplicate[idx] = True
            duplicate_group[idx] = group_id
            row_reasons = reasons[idx] or {REASON_LINKED}
            duplicate_reason[idx] = "; ".join(sorted(row_reasons))

    df["is_duplicate"] = is_duplicate
    df["duplicate_group"] = duplicate_group
    df["duplicate_reason"] = duplicate_reason
    return df
