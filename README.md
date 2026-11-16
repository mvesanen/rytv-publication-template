# rytv-publication-template

Pohja yhdelle RYTV-julkaisulle. Uusi hanke syntyy GitHubissa tästä reposta, kun asetuksista on laitettu päälle Template repository.

Moottori ei ole tässä repossa. Workflow ajaa kuvan `ghcr.io/mvesanen/rytv-builder:0.1.4`. Kuva pitää olla julkaistu ennen kuin tämä workflow onnistuu.

## Kansiot

- `markdown/` sisältää kertovan tekstin. `publication.json` kertoo, mistä tiedostosta julkaisu alkaa.
- `diagrams/` sisältää Mermaid-lähteet (`.mmd`) ja myöhemmin BPMN-kuvaukset (`.bpmn`).
- `schema/` sisältää koneluettavat vaatimukset: XSD, JSON Schema, IDS ja esimerkkisiirtotiedostot.
- `figures/` sisältää valmiit kuvat, joita buildi ei tuota.
- `artefact/` syntyy buildissa. Sitä ei talleteta git-historiaan.

## Build omalla koneella

Moottorirepo on kloonattu viereen ja sen riippuvuudet on asennettu:

```bash
python -m builder C:\Dev\rytv-publication-template
```

Kontilla, julkaisurepon juuresta:

```bash
docker run --rm -v %cd%:/publication rytv-builder
```

Tulokset ovat kansiossa `artefact/`: PDF, `html/index.html`, `machine-readable/` ja `publication-index.json`. PDF- ja HTML-ulkoasu tulevat moottorin kuvasta.

## Julkaisu

Push `main`-haaraan ja pull request jättävät paketin Actions-artefaktiksi. Ne eivät päivitä julkista sivua.

GitHub Pages on yksi sivusto:

- GitHub Release lisää version polkuun `versions/<tag>/`. Aiemmat versiot jäävät paikalleen, ja juuren luettelo näyttää uusimman ensin.
- `dev`-haara korvaa vain polun `dev/`. Sivu näyttää sen commitin viestin, ajan ja hashin. Muut haarat eivät saa omaa sivua: yksi sivusto täyttyisi vanhoista haaroista, eikä poistettu haara siivoaisi itseään.

Sivu on osoitteessa `https://<omistaja>.github.io/<repo>/`.
