# Adding more mango years (the single biggest accuracy lever)

The model has only 4 official years (2021-22 to 2024-25), so only 2 honest forecast origins exist.
More history is the best way to firm up the results.

1. Append rows to `wb_mango_district_annual.csv` with the same columns
   (state, district, crop, year, estimate_round, area_thousand_ha, production_thousand_mt, source_url).
   `source_url` must be on https://wbfpih.wb.gov.in/ . Use the same 22 district names.
2. Add the official state total for that year to `EXPECTED_TOTALS` in `app/train_mango_yield_model.py`
   (district rows must reconcile to it within published rounding).
3. Run `python -m app.train_mango_yield_model`, then `python -m pytest`.

Do not paste figures from secondary sources or OCR snippets. A year that does not reconcile to the
official state total is rejected on purpose.
