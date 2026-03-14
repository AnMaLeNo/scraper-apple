# Agent Skill : Scraper Catalogue Apple Reconditionné

## 1. Contexte de la Mission
Tu es un agent d'extraction de données opérant sous Google Antigravity. Ta mission est de concevoir un scraper robuste pour extraire les informations des produits Apple reconditionnés à partir d'une structure DOM spécifique. 

## 2. Structure HTML Cible (DOM)
Les données à extraire se trouvent au sein du conteneur parent suivant :
`<div class="rf-refurb-category-grid-no-js"><ul>...</ul></div>`

Chaque produit est encapsulé dans une balise `<li>`.

## 3. Règles d'Extraction et Sélecteurs Exacts
Pour chaque élément `<li>`, tu dois extraire et nettoyer les données en respectant scrupuleusement ces sélecteurs :

* **Nom du produit :**
    * Sélecteur : `h3 > a`
    * Action : Extraire le texte interne.
* **URL du produit :**
    * Sélecteur : `h3 > a`
    * Action : Extraire l'attribut `href` (et reconstruire l'URL absolue si nécessaire).
* **Prix Actuel :**
    * Sélecteur : `div.as-price-currentprice.as-producttile-currentprice`
    * Action : Extraire le texte. Ignorer ou nettoyer les balises invisibles pour l'accessibilité (ex: `<span class="visuallyhidden">Maintenant</span>`). Ne conserver que la valeur numérique et la devise (ex: "589,00 €").
* **Ancien Prix (si disponible) :**
    * Sélecteur : `span.as-price-previousprice`
    * Action : Extraire le texte et nettoyer le préfixe `<span class="was-text">Ancien prix : </span>`. Ne garder que la valeur (ex: "699,00 €").
* **Économie (si disponible) :**
    * Sélecteur : `span.as-producttile-savingsprice`
    * Action : Extraire le texte (ex: "Économisez 110,00 €").