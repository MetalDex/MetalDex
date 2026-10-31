# Security

MetalDex is a static page and a set of data files: there is no server, database or login to attack. The things that
could go wrong are a bad change to the data, a link or picture pointing somewhere harmful, or a problem in the
GitHub checks.

## Reporting a problem

If you find something that could hurt visitors (a harmful link, a script that shouldn't be there, a leaked secret),
please **don't open a public issue**. Use **Security → Report a vulnerability** on the repository page (a private
report only the maintainer sees). For anything else, a normal issue is fine.

## How the project protects itself

- Only the maintainer changes the repository. Everyone else reports changes with the issue forms, and pull requests
  from others are refused by the automatic check.
- Every change is checked automatically (`.github/workflows/validate.yml`): ids can't change and figures can't be
  removed, photos may only come from a short list of sites, links must be https, and text fields can't contain HTML or
  scripts.
- The page itself escapes every piece of text it shows and only follows https links from the data.
- The checks run with read-only access and no secrets; actions are pinned to exact versions and kept up to date by
  Dependabot.
- The price history is written only by the update script. Visitors report wrong prices with the "Wrong figure?"
  form; confirmed fixes go into `prices/data/corrections.csv`.
- Everything is in git, so any bad change can be reverted.
