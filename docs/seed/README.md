# Pharmacy starter catalogue

`pharmacy-catalogue.csv` in this directory is the source data for the
"starter pharmacy catalogue" feature: a ready-made list of pharmacy product
names that a newly onboarded hospital can adopt into its own inventory
instead of typing every drug in by hand.

## Format

Plain CSV, one product per row, with a `name` column:

```csv
name
Paracetamol 500mg Tablet
Amoxicillin 250mg Capsule
```

Rules:

- One product name per row. No batch numbers, no expiry dates, no
  quantities, no costs: those are per-hospital data the hospital fills in
  itself when it adopts and stocks the item.
- The `name` column is required. Extra columns are ignored, so a source
  spreadsheet with more detail can be exported as-is without stripping
  columns first.
- Duplicate names (after trimming whitespace and ignoring case) are
  collapsed to one entry; the first occurrence wins.
- Blank rows and rows with an empty `name` are skipped.

## Replacing the placeholder rows

The rows currently in this file are placeholders (marked `PLACEHOLDER`) so
the adoption code path is exercisable and the automated tests have
something to load. They are not a real product list and must not be
treated as clinical guidance.

The real catalogue replaces this file's rows wholesale: delete the
placeholder rows and drop in the real list, keeping the `name` header. No
code change is needed. If the file is ever missing or ends up with zero
usable rows, the feature degrades cleanly: the API reports the catalogue
as unavailable and the UI tells the hospital it hasn't been loaded yet,
rather than erroring.
