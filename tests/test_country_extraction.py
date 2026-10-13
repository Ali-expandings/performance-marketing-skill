import os
import sys
import unittest
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
from common import country_from_text


def extract_country_old(df, phone_fields, local_pats, country_labels):
    fields = [f for f in phone_fields if f in df.columns]
    text = df[fields].fillna("").astype(str).agg(" ".join, axis=1) if fields else pd.Series([""] * len(df), index=df.index)
    return [country_from_text(t, local_pats, country_labels) or "Unknown" for t in text.loc[df.index]]


def extract_country_new(df, phone_fields, local_pats, country_labels):
    fields = [f for f in phone_fields if f in df.columns]
    if fields:
        text = df[fields[0]].fillna("").astype(str)
        for f in fields[1:]:
            text = text + " " + df[f].fillna("").astype(str)
    else:
        text = pd.Series([""] * len(df), index=df.index)

    country_cache = {}

    def _cached_country(t):
        if not t:
            return "Unknown"
        if t not in country_cache:
            country_cache[t] = country_from_text(t, local_pats, country_labels) or "Unknown"
        return country_cache[t]

    return [_cached_country(t) for t in text.loc[df.index]]


class TestCountryExtractionRegression(unittest.TestCase):
    def setUp(self):
        self.local_pats = [{"regex": r"^01[0125]\d{8}$", "country": "Egypt (+20)"}]
        self.country_labels = {"966": "Saudi Arabia"}
        self.phone_fields = ["phone", "mobilephone"]

    def test_empty_or_missing_fields(self):
        # Case 1: Phone fields completely missing from DataFrame
        df1 = pd.DataFrame({"id": ["1", "2"], "name": ["A", "B"]})
        old_res1 = extract_country_old(df1, self.phone_fields, self.local_pats, self.country_labels)
        new_res1 = extract_country_new(df1, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_res1, new_res1)
        self.assertEqual(new_res1, ["Unknown", "Unknown"])

        # Case 2: Phone fields present but containing None, empty strings, and NaN
        df2 = pd.DataFrame({"phone": [None, "", "  "], "mobilephone": ["", None, "nan"]})
        old_res2 = extract_country_old(df2, self.phone_fields, self.local_pats, self.country_labels)
        new_res2 = extract_country_new(df2, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_res2, new_res2)

    def test_multiple_phone_fields(self):
        # Multiple phone fields where country code appears in second field or primary field
        df = pd.DataFrame({
            "phone": ["", "+201012345678", None, "01012345678"],
            "mobilephone": ["+966501234567", "", "+971501234567", None]
        })
        old_res = extract_country_old(df, self.phone_fields, self.local_pats, self.country_labels)
        new_res = extract_country_new(df, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_res, new_res)

    def test_repeated_and_mostly_unique_values(self):
        # Repeated values (cache hits)
        df_repeated = pd.DataFrame({
            "phone": ["+201012345678"] * 500 + ["+966501234567"] * 500,
            "mobilephone": [""] * 1000
        })
        old_rep = extract_country_old(df_repeated, self.phone_fields, self.local_pats, self.country_labels)
        new_rep = extract_country_new(df_repeated, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_rep, new_rep)

        # Mostly unique values (cache misses)
        df_unique = pd.DataFrame({
            "phone": [f"+2010{i:08d}" for i in range(1000)],
            "mobilephone": [""] * 1000
        })
        old_uniq = extract_country_old(df_unique, self.phone_fields, self.local_pats, self.country_labels)
        new_uniq = extract_country_new(df_unique, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_uniq, new_uniq)

    def test_duplicate_deal_ids(self):
        # DataFrame with non-standard index / duplicate IDs
        df = pd.DataFrame({
            "id": ["deal_1", "deal_1", "deal_2"],
            "phone": ["+201012345678", "+201012345678", "+966501234567"],
            "mobilephone": ["", "", ""]
        }, index=[10, 20, 30])
        old_res = extract_country_old(df, self.phone_fields, self.local_pats, self.country_labels)
        new_res = extract_country_new(df, self.phone_fields, self.local_pats, self.country_labels)
        self.assertEqual(old_res, new_res)


if __name__ == "__main__":
    unittest.main()
