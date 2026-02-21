# Redizajn sajta — Novi React interfejs

Sajt AI Vlade Crne Gore je potpuno redizajniran. Prethodni statički HTML sajt zamijenjen je modernom jednostraničnom aplikacijom izgrađenom sa React, TypeScript i Tailwind CSS tehnologijama.

Ključna poboljšanja:

- Dvojezična podrška (engleski/crnogorski) sa prekidačem za jezik na svakoj stranici
- Detaljne stranice analiza sa verdiktima ministarstava, razloženim ocjenama, kontra-prijedlozima i transkriptima parlamentarnih debata
- Poboljšana čitljivost sa čistijim rasporedom i konzistentnom tipografijom
- Brža navigacija između stranica bez potpunog ponovnog učitavanja
- Dizajn prilagođen mobilnim uređajima

Sajt se i dalje statički generiše — Python build pipeline izvozi podatke analiza kao JSON datoteke, koje React aplikacija učitava u toku rada. Nije potrebna serverska infrastruktura.
