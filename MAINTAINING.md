# Maintainer checklist

Only the maintainer changes the repository. Everyone else reports through the issue forms.

## Handling reports

- **New figure or release** / **Fix a figure**: check the source (shop page, official announcement, guide). Edit
  `data/figures.csv` and/or `data/releases.csv`, run `python3 scripts/build.py` (it checks the edit and rebuilds
  `docs/`), commit with "Fixes #<issue>" in the message, push. The issue closes itself.
  New design (different paint or sculpt) = new row in figures.csv; re-run = new row in releases.csv with
  `kind` = `rerun`. Ids are lowercase-hyphenated English and never change.
- **Wrong match**: open the listing, check, then
  `python3 prices/correct.py <listing id> <right figure id | exclude> "why" --by "#<issue>"`, rebuild, commit, close.
- **Photo submission**: check the permission box is ticked and the photo is one figure. Save it as
  `docs/img/contrib/<figure-id>.jpg`, set the figure's `image_url` to `img/contrib/<figure-id>.jpg` and
  `image_credit` to the name given (optionally `Name|https://link`), rebuild, commit.
- **Photo removal or credit change**: do it promptly; remove or change the photo in `data/figures.csv`.
- A pull request from someone else: the **Validate data** check fails it on purpose. Thank them, ask them to use an
  issue form, and close it.

## Repository settings (once the repo is public)

- Two-factor sign-in on your GitHub account.
- Settings → General → Features → Pull requests: limit to collaborators (or turn them off).
- Settings → Rules → Rulesets → new branch ruleset for `main`: block force pushes and deletion.
- Settings → Actions → General: "Require approval for all outside collaborators" for workflow runs; workflow
  permissions "Read repository contents".
- Settings → Code security: turn on Dependabot alerts, secret scanning and private vulnerability reporting.
- Never add secrets the checks don't need, and never change the workflow to `pull_request_target`.

## If something bad got in

`git revert <commit>` and push, or roll the data files back to an earlier commit. Nothing is ever lost.
