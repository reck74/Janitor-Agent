# MultiSelect API Pattern (NocoDB v2026.07+)

The `MultiSelect` field type stores a set of option-IDs per cell, but the API
surface is poorly documented and has several false starts. This reference is the
**working pattern**, derived from a real bulk-labeling task.

## TL;DR — the only working pattern

```bash
# 1. Create the column with NO initial options (the dtxp format is ignored)
curl -X POST .../api/v2/meta/tables/{TABLE_ID}/columns \
  -H "xc-token: $TOKEN" -b cookies.txt -H "Content-Type: application/json" \
  -d '{
    "column_name": "labels",
    "title": "Labels",
    "uidt": "MultiSelect",
    "description": "Free-form multi-value tags"
  }'

# 2. Add options via PATCH (NOT POST /options — that returns 404)
curl -X PATCH .../api/v2/meta/columns/{COL_ID} \
  -H "xc-token: $TOKEN" -b cookies.txt -H "Content-Type: application/json" \
  -d '{
    "colOptions": {
      "options": [
        {"title": "label-1", "color": "#44EDFE"},
        {"title": "hot-lead", "color": "#cf5c2e"}
      ]
    }
  }'

# 3. Assign values via PATCH records (send ARRAY of strings)
curl -X PATCH .../api/v2/tables/{TABLE_ID}/records \
  -H "xc-token: $TOKEN" -b cookies.txt -H "Content-Type: application/json" \
  -d '[{"Id": 5, "labels": ["label-1"]}]'
```

## What DOESN'T work (verified by curl probe)

| Endpoint | Result |
|----------|--------|
| `POST /api/v2/meta/columns/{id}/options` | **404** |
| `POST /api/v2/meta/columns/{id}/options/bulk` | **404** |
| `POST /api/v2/meta/select-options/{id}` | **404** |
| `POST /api/v2/meta/columns/{id}` with `dtxp: "'opt1','opt2'"` | Column created but `colOptions.options` is `[]` — the CSV-in-dtxp format is silently ignored |
| `POST /api/v2/meta/tables/{id}/columns` with `dtxp` set | Same as above — `colOptions.options` stays empty |

The official NocoDB docs and the Swagger UI both suggest the `/options` endpoints
exist. On v2026.07.0 self-hosted they don't. Only the PATCH path works.

## Response shape — strings, not arrays

When you read back via `GET /api/v2/tables/{id}/records`, the MultiSelect field
returns as a **comma-separated string**, not a JSON array:

```json
{
  "Id": 5,
  "labels": "label-1,hot-lead"
}
```

When you write via PATCH, send an array:

```json
[{"Id": 5, "labels": ["label-1", "hot-lead"]}]
```

Writing `"label-1,hot-lead"` (string) is **silently rejected** with a 200
response that doesn't actually update the cell. Always send arrays on writes.

To clear a MultiSelect cell, send an empty array `[]`, not `null` and not `""`.

## PATCH on options is DESTRUCTIVE — send the full list

When adding a new option to an existing MultiSelect column, you must send the
**complete** `colOptions.options` array. PATCH replaces; it doesn't merge.

```bash
# WRONG — wipes the existing options
curl -X PATCH .../api/v2/meta/columns/{COL_ID} \
  -d '{"colOptions":{"options":[{"title":"vip-contact","color":"#d4af37"}]}}'

# RIGHT — includes label-1 AND hot-lead AND the new vip-contact
curl -X PATCH .../api/v2/meta/columns/{COL_ID} \
  -d '{"colOptions":{"options":[
        {"title":"label-1","color":"#44EDFE"},
        {"title":"hot-lead","color":"#cf5c2e"},
        {"title":"vip-contact","color":"#d4af37"}
      ]}}'
```

Always read the current options list first via `GET /api/v2/meta/columns/{COL_ID}`
before PATCHing.

## Assigning the same label to hundreds of records

Bulk-assigning a single label to N records uses the same PATCH records endpoint
with an array of `{Id, labels}` payloads. Chunks of 100 work reliably:

```bash
# Build array of {Id, labels:["label-1"]} for all target records
# Send in chunks of 100 via PATCH /records
# Empirical: a few hundred records complete in under a second across 3-4 chunks
```

The PATCH endpoint accepts a top-level array body. Each element is one record
update keyed by `Id`. No need to chain calls.

## Filtering records by label

The `?where=(labels,eq,label-1)` filter syntax is **silently broken** on
v2026.07.0 — it returns 0 results even when many records have the label. Workarounds:

1. **Paginate and filter in Python** — reliable but verbose. For a few hundred
   records a single page of 100×N works.
2. **Create a Grid view** in the UI with a filter rule on `Labels` contains
   `label-1` — the view persists and you can re-query the view ID via
   the UI's REST endpoints.
3. **Add a formula column** that returns 1/0 based on label membership and
   filter on that — overengineered for one-off queries.

For programmatic filtering, paginate-and-filter-Python is the safest.

## Reading column metadata

`GET /api/v2/meta/columns/{COL_ID}` returns the full column definition including
the `colOptions.options` array with `{id, title, color, order, ...}`. Use the
option `id` (not title) as the canonical identifier if you ever need to reference
options by ID. In practice, matching by `title` is fine for human-readable labels.

## Common mistakes

| Symptom | Cause |
|---------|-------|
| Column created but PATCH on records doesn't update label | Options list was empty when you created the column. Add options first. |
| PATCH returns 200 but cell is unchanged | You sent a string instead of an array for the value. |
| `?where=...` returns 0 records | Filter syntax is broken. Paginate and filter in Python. |
| Adding a new option silently removes existing ones | You sent only the new options instead of the full list. Always GET-then-PATCH. |
| `colOptions.options` is `[]` after creation | You used `dtxp` instead of `colOptions.options` array. The docs example is wrong. |
