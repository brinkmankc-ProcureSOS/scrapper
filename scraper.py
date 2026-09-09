name: Automated Web Scraper

on:
  workflow_dispatch:
  schedule:
    - cron: '0 12 * * 1'

permissions:
  contents: write

jobs:
  run-scraper:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run Aggregator Pipeline
        run: python scraper.py

      - name: Commit and push results
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add aggregated_leads.csv
          if ! git diff --quiet || ! git diff --staged --quiet; then
            git commit -m "Update aggregated leads [skip ci]"
            git pull --rebase origin main
            git push origin main
          fi
