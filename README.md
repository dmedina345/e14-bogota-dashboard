# E14 Bogotá Dashboard

Static Spanish dashboard for exploring Bogotá E14 presidential second-round voting distributions by mesa, zona, and puesto.

## Scope

This dataset currently covers only Bogotá D.C. It does not include other Colombian departments or municipalities.

## Dashboard

The dashboard is in `site/e14-dashboard` and can be hosted as a static site.

It includes:

- Validation mode filters: strict, candidate distribution, fallback exact, fallback 5%, fallback 10%.
- Zona, puesto, relative mesa, and minimum-form filters.
- IC/AD charts by absolute mesa and relative mesa position.
- A clickable electoral-zone cartogram.
- Download links for the recommended CSV and full prediction CSV.

## Local preview

```powershell
py -3.10 -m http.server 5178 --directory site\e14-dashboard
```

Then open `http://localhost:5178`.

## Netlify

`netlify.toml` publishes `site/e14-dashboard`, so the repo can be connected directly to Netlify. It also works as a drag-and-drop static deploy using the contents of `site/e14-dashboard`.

## Method note

Mesa position is used as an ordinal proxy for age within each puesto: lower mesa numbers generally correspond to older voters and higher mesa numbers to younger voters. The dashboard does not claim exact age ranges.
