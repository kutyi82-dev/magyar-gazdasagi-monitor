# Magyar Gazdasági Monitor

Ingyenes, statikus makrogazdasági dashboard GitHub Pages, Apache ECharts és nyilvános adatforrások használatával.

## Indítás

1. Hozz létre egy nyilvános GitHub repositoryt.
2. Töltsd fel a projekt fájljait a repository gyökerébe.
3. Nyisd meg az **Actions** lapot, majd futtasd kézzel az **Update dashboard data** workflow-t.
4. A repository **Settings > Pages** részén válaszd a **Deploy from a branch** lehetőséget, `main` branch, `/ (root)` mappa.
5. Néhány percen belül az oldal elérhető lesz a GitHub Pages címen.

## Automatikus frissítés

A `.github/workflows/update-data.yml` minden nap 05:17 UTC-kor frissíti a `data/dashboard.json` fájlt. A workflow kézzel is futtatható.

## Helyi teszt

```bash
pip install -r requirements.txt
python scripts/update_data.py
python -m http.server 8000
```

Ezután nyisd meg: http://localhost:8000

## Források

Eurostat, KSH, MNB, ECB és FRED.
