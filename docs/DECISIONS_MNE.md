# Arhitektonske odluke

## ADR-001: Claude Code SDK umjesto Claude Agent SDK
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Plan je prvobitno predviđao `claude-agent-sdk`, ali dostupan paket je zapravo `claude-code-sdk` koji pokreće Claude Code CLI kao podprocese.

**Odluka**: Koristiti `claude-code-sdk` (Claude Code SDK) za orkestraciju agenata. Svaki vladini agent radi kao Claude Code podproces sa specifičnim sistemskim promptom.

**Posljedice**: Agenti su izolovani procesi. Komunikacija se odvija putem strukturiranih ulaza/izlaza (JSON). Ovo nam daje prirodan paralelizam i izolaciju grešaka.

---

## ADR-002: Pydantic v2 za sve modele podataka
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Potrebni su strukturirani, validirani podaci koji teku između agenata.

**Odluka**: Svi podaci između agenata koriste Pydantic v2 modele sa strogom validacijom.

**Posljedice**: Tipska bezbjednost kroz cijeli tok obrade. Jednostavna JSON serijalizacija za komunikaciju između agenata.

---

## ADR-003: Arhitektura sa dva flota
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Potrebni su i AI agenti za rad u realnom vremenu (vladina simulacija) i razvojni alati.

**Odluka**:
- Flot 1 (Vladino ogledalo): Python agenti orkestrirani putem Claude Code SDK — ministarstveni podagenti koji analiziraju odluke
- Flot 2 (Razvojni flot): Claude Code instance sa `CLAUDE.md` promptovima specifičnim za ulogu (programer, recenzent, projekt menadžer)

**Posljedice**: Čisto razdvajanje između proizvoda (vladina simulacija) i razvojnog procesa. Članovi razvojnog flota mogu raditi na kodu sa specijalizovanom stručnošću.

---

## ADR-004: anyio za asinhronu konkurentnost
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Potrebno je pokretati više ministarstvenih agenata paralelno radi performansi.

**Odluka**: Koristiti `anyio` umjesto sirovog `asyncio` za sve asinhrone operacije.

**Posljedice**: Asinhron kod nezavisan od pozadinskog izvršioca. Čistiji API za grupe zadataka pri paralelnom pokretanju agenata.

---

## ADR-005: Fokus na Vladu Crne Gore
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Potrebna je konkretna vlada za ogledalo kako bi se postigli konkretni, provjerljivi rezultati.

**Odluka**: Fokusirati se na Crnu Goru kao ciljnu vladu sa 5 početnih analitičkih oblasti: Finansije, Pravosuđe, EU integracije, Zdravstvo, Unutrašnji poslovi. Ove oblasti predstavljaju područja analize politike, a ne replikaciju organizacione strukture Crne Gore od 25 ministarstava. Projekat odražava vladinu *funkciju* (analiziranje odluka iz svih oblasti politike), a ne njen *organizacioni dijagram*.

**Posljedice**: Promptovi i izvori odluka su specifični za Crnu Goru. Arhitektura je dovoljno opšta da se kasnije prilagodi drugim vladama. Buduće proširenje domena treba da prioritizuje analitičku pokrivenost i konsolidaciju umjesto da prati napuhanu strukturu stvarne crnogorske vlade.

---

## ADR-006: Razvojni tok zasnovan na PR-ovima
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Rad razvojnog flota odvijao se putem interaktivnih Claude Code sesija bez automatizovane petlje za pregled. Trebao je način da agenti programer i recenzent sarađuju kroz strukturiranu iteraciju zasnovanu na PR-ovima.

**Odluka**: Izgraditi `scripts/pr_workflow.py` — automatizovanu petlju u kojoj:
- Agenti programer i recenzent komuniciraju putem GitHub PR-ova, ne putem dijeljene memorije
- Svako pozivanje agenta je nov Claude Code SDK podproces (bez kontinuiteta sesije)
- Stanje živi na GitHub-u (grana, PR, komitovi, komentari pregleda)
- Recenzent ne može mijenjati kod (Write/Edit isključeni iz dozvoljenih alata)
- Maksimalan broj rundi (podrazumijevano 3) sprječava nekontrolisane petlje

**Posljedice**: Rad je u potpunosti sljedljiv u GitHub istoriji. Recenzent ostaje pošten (samo čitanje). Svaka runda ima svjež kontekst, izbjegavajući zastarjelo stanje. Tok rada može da radi bez nadzora, ali ima sigurnosno ograničenje.

---

## ADR-007: Autonomna petlja za samounapređenje
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: PR tok rada automatizuje cikluse programer-recenzent, ali je odabir zadataka i dalje ručni. Želimo da se projekat unapređuje autonomno: da predlaže poboljšanja, trijažira ih i izvršava u kontinuiranoj petlji.

**Odluka**: Izgraditi `scripts/self_improve.py` — spoljašnju petlju oko `pr_workflow.py` koja:
- **Predlaže**: PM agent čita status projekta i predlaže N poboljšanja po ciklusu (razvojni + vladini domeni)
- **Debatuje**: Dijalektika dva agenta (PM zagovornik vs Recenzent skeptik) sa determinističkim sudijom — bez trećeg LLM poziva za ocjenjivanje
- **Prati putem GitHub Issues**: Svaki prijedlog postaje issue; debate se objavljuju kao komentari; oznake prate životni ciklus (proposed → backlog → in-progress → done/failed)
- **Ljudski unos**: Ljudi mogu slati sugestije putem issue-a sa oznakom `human-suggestion`, koje se trijažiraju zajedno sa AI prijedlozima
- **Izvršava**: Uvozi `run_workflow` direktno (bez podprocesa) sa `Closes #N` u zadatku za automatsko povezivanje PR-ova sa issue-ima
- **Deduplikuje**: Naslovi neuspjelih zadataka se prosljeđuju ideacionom promptu radi sprječavanja ponovnog predlaganja
- **FIFO odabir**: Najstariji issue iz bekloga se izvršava prvi; trijaža već filtrira kvalitet
- **Konfigurisana bezbjednost**: `--max-cycles`, `--cooldown`, `--dry-run`, `--max-pr-rounds`

**Posljedice**: Projekat može da radi bez nadzora i kontinuirano se unapređuje. Sve odluke su javno sljedljive na GitHub-u (issue-i, komentari, PR-ovi). Mehanizam debate sprječava da nekvalitetni prijedlozi troše vrijeme izvršavanja. Ljudske sugestije su punopravni učesnici u toku trijaže.

---

## ADR-008: Docker izolacija za petlju samounapređenja
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Petlja za samounapređenje radi sa `bypassPermissions` i izvršava proizvoljne komande putem Claude Code SDK podprocesa. Pokretanje na domaćem računaru izlaže privatne podatke (SSH ključeve, `.netrc`, ostale repozitorijume) autonomnoj petlji.

**Odluka**: Dokerizovati petlju za samounapređenje sa sljedećim svojstvima izolacije:
- Kontejner vidi samo svjež git klon (bez montiranja fajl sistema domaćeg računara)
- Samo dva resursa domaćeg računara su izložena: `GH_TOKEN` env varijabla i `~/.claude` montiranje (za osvježavanje OAuth tokena)
- `init: true` (tini kao PID 1) za pravilno rukovanje signalima sa `os.execv`
- Fiksni korisnik `aigov` (UID 1000) definisan u Dockerfile-u — bez zaobilaženja UID-a u runtimeu
- Ograničenja resursa (4 CPU-a, 8GB RAM) sprječavaju nekontrolisanu potrošnju
- `on-failure:3` politika restartovanja za oporavak od padova bez beskonačnih petlji
- `uv sync` dodat u `_reexec()` tako da se promjene zavisnosti iz spojenih PR-ova instaliraju prije sljedećeg ciklusa

**Posljedice**: Autonomna petlja je izolovana u sandboxu — čak i sa `bypassPermissions`, ne može pristupiti tajnama domaćeg računara, drugim repozitorijumima ili sistemskoj konfiguraciji. Kompromis je teža slika (~1GB) zbog Node.js i Claude Code CLI zavisnosti, i nešto sporije pokretanje zbog svježeg klona pri svakom pokretanju kontejnera.

---

## ADR-010: GitHub Pages statički sajt sa Jinja2
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Projekat proizvodi AI kabinetske analize, ali nema javni izlaz. Mapa puta (Faza 4) predviđa HTML/statički sajt izlaz prilagođen vebu.

**Odluka**: Izgraditi statički sajt koristeći Jinja2 šablone (bez SSG okvira):
- Šabloni se nalaze u `site/templates/`, statički resursi u `site/static/`, obavještenja u `site/content/`
- `SiteBuilder` klasa sastavlja izvještajne kartice, indeks, stranicu „O nama" (renderuje Ustav) i stranice feeda
- `scripts/build_site.py` CLI čita serijalizovane rezultate iz `output/data/*.json`
- GitHub Actions deplojuje na GitHub Pages pri push-u na main granu
- `SessionResult` konvertovan iz `@dataclass` u Pydantic `BaseModel` radi omogućavanja `.model_dump_json()`
- Glavna petlja serijalizuje rezultate u `output/data/` nakon svake analize
- Sajt korisnički interfejs na crnogorskom (oznake navigacije, naslovi, podnožje)

**Razmatrane alternative**:
- SSG okviri (Hugo, Jekyll, MkDocs) — odbijeno: dodaje zavisnost od alata, sajt ima <100 stranica, Jinja2 je već Python-nativan
- SPA (React/Vue) — odbijeno: nepotrebna složenost za sajt sa sadržajem
- Server-renderovano — odbijeno: troškovi hostinga, GitHub Pages je besplatan i odgovara slučaju upotrebe

**Posljedice**: Nema novih alata osim Jinja2 (već Python zavisnost). Potpuna rekonstrukcija pri svakom deploju (prihvatljivo za mali sajt). Inkrementalne gradnje mogu se dodati kasnije po potrebi. Direktorijum `output/data/` je komitovan u git tako da tok deploja može da ga čita.

---

## ADR-009: Objedinjena glavna petlja
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Projekat je imao dvije odvojene ulazne tačke: `self_improve.py` (beskonačna petlja za unapređenje koda) i `run_session.py` (jednokratna vladina analiza). Trebalo ih je objediniti tako da jedan Docker kontejner može oboje: analizirati vladine odluke I unapređivati sebe.

**Odluka**: Preimenovati `self_improve.py` u `main_loop.py` i dodati trofazni ciklus:
- **Faza A**: Provjera novih vladinih odluka (iz seed podataka, ubuduće: skrejperi) i kreiranje `task:analysis` issue-a u objedinjenom beklogu
- **Faza B**: Samounapređenje — predlaganje poboljšanja, debata i dodavanje prihvaćenih prijedloga u beklog kao i ranije
- **Faza C**: Odabir iz objedinjenog bekloga (analitički zadaci imaju prioritet) i usmjeravanje po tipu zadatka: `task:analysis` pokreće pipeline orkestratora, sve ostalo pokreće pr_workflow

Analitički zadaci preskaču debatu (analiziranje stvarnih odluka je uvijek ispravna stvar). Obje faze se mogu nezavisno preskočiti putem `--skip-analysis` i `--skip-improve`. Funkcija `get_pending_decisions()` trenutno učitava iz seed podataka i predstavlja integracionu tačku za skrejpere u Fazi 3.

**Posljedice**: Jedan proces obrađuje i proizvod (vladina analiza) i meta-proces (samounapređenje). Docker env varijable preimenovane iz `SELF_IMPROVE_*` u `LOOP_*`. CLI `run_session.py` ostaje dostupan za jednokratnu analizu van petlje.

---

## ADR-011: X dnevni pregled umjesto niti po analizi
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Projekat je imao `social_media.py` formater koji je proizvodio višetvitovske niti po analizi, ali ništa zapravo nije objavljivano na X. Cilj je automatizovano objavljivanje na X sa minimalnim šumom (maksimalno 1-2 objave dnevno).

**Odluka**: Objavljivati jedan dnevni pregled (digest) tvit umjesto niti po analizi:
- Kompozicija zasnovana na šablonu (bez LLM poziva) — bira do 3 najzabrinjavajuća rezultata sortiranih po `decision_score` kritičara uzlazno
- 24h pauza između objava, kontrolisana lokalnim fajlom stanja (`output/twitter_state.json`)
- Graciozna degradacija: ako `TWITTER_*` env varijable nijesu postavljene, objavljivanje se tiho preskače; glavna petlja nikad ne pada zbog X-a
- OAuth 1.0a putem tweepy za objavljivanje (Bearer Token je app-only/samo za čitanje)
- Sadržaj objave se uvijek loguje u konzolu, čak i kad akreditivi nijesu konfigurisani

**Razmatrane alternative**:
- Objavljivanje niti po analizi — odbijeno: previše šuma, korisnik želi maksimalno 1-2 objave dnevno
- LLM-generisan tekst tvita — odbijeno: dodaje troškove API-ja, latenciju i nepredvidivost za determinističan zadatak formatiranja
- Provjera X API-ja za vrijeme poslednje objave — odbijeno: nepotrebni API pozivi kad lokalni fajl stanja dovoljno služi

**Posljedice**: Predvidivo, niskošumno prisustvo na X-u. Postojeći `social_media.py` formater niti ostaje dostupan za buduću upotrebu (npr. ručno objavljivanje, druge platforme). Razvojna okruženja rade bez X akreditiva.

---

## ADR-012: Slojevita arhitektura kontraprijedloga
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: AI Vlada kritikuje i ocjenjuje vladine odluke, ali nikad ne predlaže alternative. Da bi djelovala kao istinsko paralelno upravljačko tijelo, treba da kaže „evo šta bismo mi uradili umjesto toga."

**Odluka**: Koristiti slojeviti pristup:
1. Svako ministarstvo proizvodi kontraprijedlog specifičan za domen kao dio svoje postojeće analize (isti API poziv, bez dodatnih troškova — samo više izlaznih tokena)
2. Novi `SynthesizerAgent` konsoliduje ministarstvene kontraprijedloge u jedan objedinjeni kontraprijedlog (+1 API poziv po odluci)

Promjene pipeline-a sa 7 → 8 API poziva:
```
Prije: Odluka → 5 ministarstava (paralelno) → parlament + kritičar (paralelno) → izlaz
Poslije: Odluka → 5 ministarstava sa kontraprijedlozima (paralelno) → parlament + kritičar (paralelno) → sintetizator → izlaz
```

Sva nova polja modela su opciona (`None` podrazumijevano) radi kompatibilnosti unazad sa postojećim serijalizovanim podacima.

**Razmatrane alternative**:
- Jedan sintetizator bez ministarstvenih prijedloga — odbijeno: gubi se domenski specifična stručnost, a ministarstva već imaju kontekst tokom analize
- Paralelni sintetizator sa Fazom 2 — odbijeno: zadržavanje sekvencijalnog (Faza 3) ostavlja mogućnost da se rezultati parlamenta/kritičara kasnije proslijede sintetizatoru
- Odvojeni API poziv po ministarstvu za kontraprijedloge — odbijeno: rasipnički kad isti kontekst već postoji u ministarstvenom analitičkom pozivu

**Posljedice**: ~14% povećanja troškova (8 naspram 7 API poziva). Ministarstveni kontraprijedlozi su suštinski besplatni (isti poziv, ~15-20% više izlaznih tokena). Objedinjeni kontraprijedlog daje projektu identitet paralelnog upravljačkog tijela, a ne samo kritičara.

---

## ADR-013: GitHub Projects kao prezentacioni sloj
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Glavna petlja prati stanje toka rada issue-a putem GitHub oznaka (`self-improve:proposed` → `backlog` → `in-progress` → `done/failed/rejected`). Ovo pouzdano funkcioniše za agente, ali ne pruža vizuelni pregled za ljude. Kanban tabla bi omogućila održavaocima da vide tok na prvi pogled.

**Odluka**: Dodati GitHub Projects integraciju kao **prezentacioni sloj** na vrh postojećeg sistema oznaka:
- Jedan projekat ("AI Government Workflow") sa Status poljem koje odražava stanja oznaka, plus Task Type i Domain polja za metapodatke
- Oznake ostaju izvor istine — agenti čitaju/pišu oznake, polja projekta se ažuriraju kao nuspojava
- Svi API pozivi za projekat su nefatalni (`check=False`, umotani u try/except) tako da greške nikad ne kvare glavnu petlju
- Postavljanje projekta (kreiranje projekta, kreiranje polja, keširanje ID-jeva) pokreće se jednom po ciklusu u `ensure_github_resources_exist()`
- Upravljano kodom putem `gh project` CLI komandi — bez zavisnosti od GitHub Automations

**Razmatrane alternative**:
- GitHub Automations (ugrađene automatizacije projekta) — odbijeno: ograničene na mapiranje oznaka u statuse, bez kontrole prilagođenih polja, netransparentne za debagovanje
- Odvojeni alat za praćenje (Linear, Jira) — odbijeno: dodaje spoljašnju zavisnost, GitHub Issues već koriste agenti
- Samo oznake (status quo) — odbijeno: funkcioniše za agente, ali slaba vidljivost za ljude

**Posljedice**: Ljudi dobijaju kanban tablu i tabelarni prikaz bez mijenjanja ponašanja agenata. OAuth opseg `project` mora biti odobren tokenu (`gh auth refresh -s project`). Prikazi table/tabele se konfiguršu ručno u GitHub veb interfejsu (jednokratno postavljanje). Nešto više API poziva po tranziciji oznake (~1-3 dodatna poziva po promjeni statusa), ali svi su neblokirajući.

---

## ADR-014: Diskusije kao površina isključivo za ljude
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: GitHub Discussions i Wiki su omogućeni na repozitorijumu. Projekat je trebao odlučiti kako (ili da li) ih koristiti uz postojeći praćenje issue-a vođen agentima i GitHub Pages statički sajt.

**Odluka**:
- **Diskusije: usvojene kao površina isključivo za ljude.** Četiri kategorije: Obavještenja (ažuriranja održavaoca), Prijedlozi odluka (građani predlažu odluke), Metodologija (pitanja i odgovori o ocjenjivanju/agentima), Ispravke (prijavljivanje činjeničnih grešaka po Ustavu čl. 24). Bez integracije sa agentima — održavalac ručno trijažira Diskusije u Issue-e kada je prikladno.
- **Wiki: onemogućen.** Duplira `docs/` i statički sajt, nije verzionisan i agenti ga ne mogu programski održavati.
- **Jezička politika**: Backend, agenti, dokumentacija, fajlovi zajednice i struktura Diskusija ostaju na engleskom. Statički sajt (GitHub Pages) koristi crnogorski sa pravilnim dijakritičkim znacima (č, ć, š, ž, đ) i ijekavskim dijalektom. Korisnički generisan sadržaj u Diskusijama može biti na crnogorskom.
- **Issue šabloni sa contact_links** preusmjeravaju konverzaciona pitanja ka Diskusijama, održavajući praćenje issue-a čistim za mašinu stanja agenata.

**Razmatrane alternative**:
- Diskusije vođene agentima (automatsko objavljivanje analiza, automatski odgovori) — odbijeno: Diskusije su namijenjene za ljudsku konverzaciju; šum agenata bi obeshrabrio učešće
- Wiki za dokumentaciju — odbijeno: nije verzionisan, duplira postojeću dokumentaciju, agenti ga ne mogu održavati
- Fajlovi zajednice na crnogorskom — odbijeno: saradnici/programeri trebaju engleski; samo javni sajt cilja crnogorske građane

**Posljedice**: Čisto razdvajanje između ljudske konverzacije (Diskusije) i toka rada agenata (Issue-i). Praćenje issue-a ostaje strukturirano i čitljivo za mašine. Građani dobijaju posvećen prostor za predlaganje odluka i prijavljivanje grešaka bez potrebe da razumiju pipeline agenata. Nije potrebna promjena koda glavne petlje.

---

## ADR-015: Agent Projektni direktor za operativni nadzor
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Glavna petlja radi autonomno, ali nema mehanizam povratne informacije na meta nivou. Kada se dogode sistemski problemi (ponavljajuće greške PR-ova, uzaludne debate, zaglavljeni issue-i, bagovi recenzenta), nijedan agent ih ne detektuje niti ispravlja — čovjek mora ručno da prati i prijavljuje issue-e.

**Odluka**: Dodati agenta Projektnog direktora (Faza D) koji periodično pregleda telemetriju ciklusa i prijavljuje ciljana procesna poboljšanja:

- **Sjevernjača: Prinos ciklusa** — udio ciklusa koji proizvode spojeni PR, objavljenu analizu ili objavljeni pregled. Nije moguće manipulisati (prijavljivanje više issue-a ne pomaže), obuhvata ono što je bitno (sistem postoji da proizvodi rezultate).
- **Telemetrija**: `CycleTelemetry` Pydantic model perzistiran kao JSONL (`output/data/telemetry.jsonl`). Svaki ciklus je instrumentalizovan sa vremenima faza, uspjehom/neuspjehom, greškama i statusom prinosa.
- **Četvoroslojni otporni sistem**: (L1) nikad ne srušiti petlju — zaštita od pada na najvišem nivou piše parcijalnu telemetriju; (L2) zabilježiti sve greške u telemetriji; (L3) automatski prijaviti issue-e stabilnosti za ponavljajuće obrasce grešaka (mehanički, bez LLM-a); (L4) Docker `restart: unless-stopped`.
- **Direktor NEMA alate** (`allowed_tools=[]`) — sav kontekst je unaprijed pribavljen i ubačen u prompt. Sprječava nekontrolisane komande.
- **5-nivojski prioritet**: analiza > ljudski > strategija (#83) > direktorski > FIFO.
- **Tvrdo ograničenje od 2 issue-a** po pregledu Direktora, implementirano u kodu bez obzira na izlaz agenta.
- **Pokreće se svakih N ciklusa** (podrazumijevano 5, konfigurisano putem `--director-interval`). Treba akumulirane podatke.
- **Podešavanje agenata**: Direktor može prijaviti issue-e za prilagođavanje promptova agenata kojima upravlja (PM, Programer, Recenzent). Ne može mijenjati sopstveni prompt ili agente višeg nivoa.

**Razmatrane alternative**:
- Direktor sa pristupom alatima — odbijeno: pretpribavljanje je bezbjednije i sprječava neograničeno istraživanje
- Direktor svaki ciklus — odbijeno: nema dovoljno podataka za uočavanje obrazaca, nepotreban trošak
- Direktor kao odvojeni proces — odbijeno: čvrsta integracija sa glavnom petljom je jednostavnija i obezbjeđuje pristup telemetriji

**Posljedice**: Sistem može da detektuje i ispravi sopstvene operativne probleme bez ljudske intervencije. Telemetrija pruža uvid u zdravlje petlje. Prekidač strujnog kola (Sloj 3) hvata ponavljajuće greške brže od čekanja na periodični pregled Direktora. Oznaka `strategy-suggestion` je rezervisana za budućeg Strateškog direktora (#83).

---

## ADR-016: Agent News Scout umjesto prilagođenih skrejpera
**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Faza 3 (Unos stvarnih podataka) predviđala je MCP skrejper servere (`gov_me_scraper.py`, `news_scraper.py`) za skrejpovanje gov.me i novinskih portala. Izgradnja i održavanje prilagođenih skrejpera je krhko — sajtovi mijenjaju izgled, zahtijevaju rukovanje autentifikacijom i trebaju logiku parsiranja za svaki izvor.

**Odluka**: Zamijeniti prilagođene skrejpere jednim News Scout agentom koji koristi Claude-ove ugrađene `WebSearch` i `WebFetch` alate za otkrivanje i čitanje vijesti. Ključne dizajnerske tačke:
- **Zasnovano na agentu, ne na skripti**: Claude Code SDK agent sa `WebSearch` + `WebFetch` otkriva i parsira vijesti. Bez prilagođenog koda za skrejpovanje.
- **Jednom dnevno**: Fajl stanja (`output/news_scout_state.json`) prati datum poslednjeg pribavljanja. Preskače ako je već pribavljeno danas.
- **Ograničeno na 3 odluke**: Prioritizovano po javnom interesu radi kontrole troškova analize.
- **Deterministički ID-jevi**: `news-{date}-{sha256(title)[:8]}` sprječava dupliranu analizu issue-a.
- **Samostalni issue-i**: Kompletan `GovernmentDecision` JSON ugrađen u tijelo GitHub issue-a. Korak izvršavanja parsira direktno iz issue-a.
- **Seed podaci očuvani**: Seed odluke se i dalje učitavaju kao zamjena/dopuna.
- **Nefatalno**: Greška News Scout-a ne ruši petlju.
- **Bez politike skrejpovanja**: MCP skrejper stubovi izbrisani. Eksplicitna politika protiv skripti za skrejpovanje u `mcp_servers/__init__.py` i `CLAUDE.md`.

**Razmatrane alternative**:
- Prilagođeni MCP skrejperi po izvoru — odbijeno: krhko, zahtijeva mnogo održavanja, zahtijeva parsiranje HTML-a za svaki sajt
- RSS/Atom feedovi — odbijeno: nemaju svi crnogorski izvori pouzdane feedove za vladine vijesti
- API-ji trećih strana za vijesti — odbijeno: ograničena pokrivenost odluka crnogorske vlade

**Posljedice**: Nema koda za skrejpovanje koji treba održavati. Agent se automatski prilagođava promjenama sajtova. Kompromis je oslanjanje na kvalitet Claude-ove veb pretrage za crnogorske izvore i veći trošak po pribavljanju (jedno pozivanje agenta naspram determinističkih HTTP zahtjeva). Ograničavanje na 3 odluke dnevno ograničava troškove.

---

## ADR-017: Urednički direktor za kontrolu kvaliteta analiza
**Datum**: 2026-02-15
**Status**: Prihvaćeno

**Kontekst**: Nijedan agent ne prati da li su objavljene analize tačne, ubjedljive ili da li odjekuju u javnosti. Bez nadzora kvaliteta, rizikujemo objavljivanje sadržaja niskog uticaja ili sa greškama. Strateški direktor (#122) je identifikovao ovaj nedostatak sposobnosti.

**Odluka**: Dodati agenta Uredničkog direktora koji pregledava završene analize u pogledu:
1. **Činjenična tačnost** — bez grešaka, pogrešnih tumačenja ili nepotkrijepljenih tvrdnji
2. **Kvalitet narativa** — jasna struktura, logičan tok, privlačno za opštu čitalačku publiku
3. **Javna relevantnost** — bavi se brigama građana, uvidi na koje se može djelovati
4. **Ustavna usklađenost** — transparentnost, borba protiv korupcije, fiskalna odgovornost
5. **Potencijal angažovanja** — prati koje teme/okviri rezonuju (kada metrike budu dostupne)

**Implementacija**:
- Prompt uloge: `theseus-fleet/editorial-director/CLAUDE.md`
- Model: `EditorialReview` (oznaka odobrenja, ocjena kvaliteta 1-10, prednosti, problemi, preporuke)
- Integracija: Pokreće se u `step_execute_analysis()` nakon završetka orkestratora, ali prije označavanja issue-a kao završenog
- Neblokirajuće: Greške pregleda su nefatalne. Ako nije odobreno, prijavljuje `editorial-quality` issue i nastavlja sa objavljivanjem
- Izlaz: JSON pregled sa statusom odobrenja, ocjenom kvaliteta i primjenljivim povratnim informacijama

**Razmatrane alternative**:
- Ručni ljudski pregled — odbijeno: ne skalira se, dodaje latenciju
- Analiza kvaliteta nakon objavljivanja — odbijeno: bolje je uhvatiti probleme prije objavljivanja
- Provjere kvaliteta u postojećim agentima — odbijeno: razvodnjava fokus svakog agenta, nema objedinjenog standarda kvaliteta
- Blokiranje objavljivanja pri neuspjehu — odbijeno: stvara usko grlo, bolje je označiti i nastaviti

**Posljedice**:
- Jedan dodatni API poziv po analizi (pokreće se nakon završetka analize)
- Problemi kvaliteta se prate putem GitHub issue-a sa oznakom `editorial-quality`
- Povratna petlja omogućava kontinuirano unapređenje kvaliteta analiza
- Kada budu dostupne metrike društvenih mreža/angažovanja, Urednički direktor može identifikovati koje teme/okviri generišu najveći javni interes
- Neblokirajući dizajn obezbjeđuje da sistem nastavi da radi čak i ako pregled ne uspije

---

## ADR-018: Ograničenje nultog budžeta kao pokretač dizajna

**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Ovaj projekat nema finansiranje. Nema grantova, sponzora ni prihoda. Svaki izbor alata mora uzeti u obzir činjenicu da projekat radi na ličnim resursima održavaoca i besplatnim nivoima usluga.

**Odluka**: Tretirati nulti budžet kao prvorazredno arhitektonsko ograničenje, a ne privremeno stanje:
- **GitHub kao platforma**: Issues (praćenje zadataka), Actions (CI/CD), Pages (hosting), Projects (kanban), Discussions (zajednica) — sve besplatno za javne repozitorijume
- **Bez plaćene infrastrukture**: Bez baza podataka, servera, SaaS pretplata. Stanje živi u gitu, fajlovima i GitHub-ovom besplatnom nivou
- **Docker za lokalno izvršavanje**: Glavna petlja radi na ličnom hardveru ili besplatnim CI minutima, ne na cloud VM-ovima
- **Claude API je jedini varijabilni trošak**: Svi ostali alati su besplatni. Ovo fokusira upravljanje troškovima na jednu dimenziju

**Posljedice**: Projekat je reproduktivan od strane bilo koga ko ima Claude API ključ i GitHub nalog. Nema zaključavanja kod dobavljača osim GitHub-a (koji je ujedno i mehanizam transparentnosti — vidi ADR-019). Ograničenje forsira jednostavnost: ako funkcionalnost zahtijeva plaćenu infrastrukturu, mora se opravdati u odnosu na alternativu da ne postoji. Kompromis: besplatni nivoi imaju ograničenja brzine (GitHub API: 5.000 zahtjeva/sat autentifikovano, 500 za kreiranje sadržaja/sat; Actions: 2.000 minuta/mjesečno) koja ograničavaju propusnost.

---

## ADR-019: GitHub kao mehanizam transparentnosti, ne samo pogodnost

**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Projekat koristi GitHub Issues za koordinaciju agenata, PR-ove za promjene koda i Actions za automatizaciju. Ovo bi se moglo posmatrati kao podrazumijevani inženjerski izbor — GitHub je ono po šta programeri posežu. Ali za ovaj projekat, taj izbor je nosivi.

**Odluka**: GitHub je koordinacioni sloj *zato što je podrazumijevano javan*. Ovo direktno služi Ustavu (čl. 5: „pokaži svoje zaključivanje", čl. 22: „metodologija, izvorni kod, promptovi i analitički okvir su javni"):
- Svaki prijedlog agenta, debata i presuda je GitHub Issue komentar — vidljiv svakome
- Svaka promjena koda prolazi kroz PR sa povratnom informacijom recenzenta — revizijski sljedljiva
- Odluke petlje samounapređenja su sljedljive: zašto je ovaj zadatak predložen? Kakva je bila debata? Ko ga je odobrio?
- Projektna tabla pokazuje na čemu sistem radi, upravo sada, u realnom vremenu

Ovo je oblik **stigmergije** — indirektna koordinacija kroz dijeljeno, vidljivo okruženje. Agenti ne šalju poruke jedni drugima; ostavljaju tragove (issue-e, oznake, komentare) koje drugi agenti čitaju. Javnost čita iste tragove.

**Razmatrane alternative**:
- Interni red zadataka (Redis, SQLite) — odbijeno: brže, ali netransparentno. Građani ne mogu vidjeti red
- Linear/Jira — odbijeno: dodaje trošak, premješta koordinaciju iza zida za prijavljivanje
- Koordinacija zasnovana na fajlovima — odbijeno: nije vidljivo bez direktnog čitanja repozitorijuma

**Posljedice**: Operativna transparentnost projekta je automatska, ne performativna. Nema posebnog „izvještaja o transparentnosti" koji treba pisati — rad *je* izvještaj. Kompromis: latencija GitHub API-ja (200-500ms po pozivu naspram <1ms za fajl I/O), ograničenja brzine i činjenica da je GitHub američka korporacija koja hostuje crnogorski projekat od javnog interesa. Prednost transparentnosti prevazilazi ove troškove.

---

## ADR-020: Odabir modela — kompromis kvalitet naspram troškova

**Datum**: 2026-02-15
**Status**: Predloženo

**Kontekst**: Projekat koristi Claude modele za sav rad agenata. Modeli najvišeg kvaliteta (Opus) proizvode najbolju analizu, ali koštaju znatno više po tokenu. Rutinski zadaci (upravljanje oznakama, formatiranje šablona, parsiranje issue-a) ne trebaju zaključivanje modela na granici mogućnosti.

**Odluka**: Višenivojski odabir modela zasnovan na kritičnosti zadatka:
- **Analitički agenti** (ministarstva, parlament, kritičar, sintetizator): Koristiti najbolji dostupni model. Oni proizvode javni izlaz koji definiše kredibilitet projekta. Smanjenje kvaliteta ovdje podriva misiju
- **Razvojni flot** (programer, recenzent, PM): Koristiti sposobne, ali ekonomične modele. Kvalitet koda je bitan, ali se verifikuje CI-jem i petljama pregleda — greške se hvataju
- **Direktori** (projektni, strateški, urednički): Koristiti visokokvalitetne modele. Donose procjene o tome na čemu raditi i da li rezultati zadovoljavaju standarde
- **News Scout**: Koristiti sposobne modele. Treba razumijevanje veba i novinarska procjena, ali se izlaz pregleda prije objavljivanja
- **Rutinske operacije** (parsiranje issue-a, tranzicije oznaka, renderovanje šablona): Bez LLM poziva tamo gdje deterministički kod dovoljan

**Posljedice**: Najskuplje operacije su one koje su najvažnije — javno dostupna analiza. Trošak se skalira prvenstveno sa brojem odluka analiziranih po danu (ograničen na 3 od strane News Scout-a). Ciklusi samounapređenja su sekundarni pokretač troškova i mogu se regulisati putem `--max-cycles` i `--cooldown`. Projekat treba da prati troškove po ciklusu u telemetriji radi informisanja budućih odluka o odabiru modela.

---

## ADR-021: Monorepo — motor i aplikacija su jedan organizam

**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Projekat ima dva konceptualna sloja: (1) vladini analitički agenti koji proizvode javni izlaz, i (2) samounapređujući meta-sloj (direktori, PM, programer, recenzent, glavna petlja) koji razvija sistem. Ovi slojevi bi se mogli razdvojiti u dva repozitorijuma — „motor za samounapređujuće agente" za višekratnu upotrebu i „aplikacija za vladinu analizu" specifična za domen.

**Odluka**: Zadržati sve u jednom repozitorijumu. Slojevi nijesu razdvojivi u praksi:
- **Motor modifikuje aplikaciju**: Agent programer kreira PR-ove koji mijenjaju promptove ministarstava, modele analize i šablone izlaza. PR-ovi između repozitorijuma bi dodali značajnu složenost
- **`_reexec()` pretpostavlja jedan repo**: `git pull --ff-only && os.execv()` restartuje proces sa novim kodom. Koordinacija povlačenja između dva repozitorijuma kvari ovo
- **GitHub Issues obuhvataju oba sloja**: Jedan issue može se ticati kvaliteta analize (aplikacija) i podešavanja promptova (motor). Jedan praćenje issue-a je jednostavnije od referenci između repozitorijuma
- **Mehanizam transparentnosti je opsegovan na repo**: Jedan javni repo = jedno mjesto za građane da posmatraju cijeli sistem
- **Motor nije domenski neutralan**: Ključni dizajnerski izbori (GitHub za transparentnost, Ustav kao signal nagrade, javna vidljivost) su vođeni misijom vladine analize. Izvlačenje „generičkog" motora bi uklonilo njegova najistaknutija svojstva

**Razmatrane alternative**:
- Dva repozitorijuma (motor + aplikacija) — odbijeno: samomodifikacija između repozitorijuma je značajno složenija; dizajn motora je specifičan za misiju; ne postoji drugi domen koji bi opravdao izvlačenje
- Monorepo sa čvrstim internim granicama (odvojeni paketi) — razmatranje za budućnost: ako se motor pokaže generalizabilnim, izvući tada, sa prednosti poznavanja stvarnih granica

**Posljedice**: Jednostavniji rad, jednostavniji CI, jedinstven revizijski trag. Cijena je što projekat izgleda kao jedan veliki sistem umjesto kompozitnog alata. Ovo je prihvatljivo jer on *jeste* jedan sistem — samounapređenje i analiza koevoluiraju.

---

## ADR-022: Metrike angažovanja kao validacija, ne cilj optimizacije

**Datum**: 2026-02-15
**Status**: Predloženo

**Kontekst**: Projekat objavljuje dnevne preglede na X i objavljuje izvještajne kartice na sajtu. Angažovanje na društvenim mrežama (lajkovi, retvitovi, odgovori) i saobraćaj na sajtu su mjerljivi signali. Iskušenje je optimizovati za ove metrike — juriti angažovanje da bi se „dokazao" uticaj.

**Odluka**: Tretirati metrike angažovanja kao **signal validacije** (da li ljudi ovo čitaju?) a ne kao **cilj optimizacije** (kako da dobijemo više klikova?):
- Pratiti podatke o angažovanju kad su dostupni, ali ih ne ubacivati u petlje nagrađivanja agenata
- Ne mijenjati okvir analize, odabir tema ili ton radi povećanja angažovanja
- Ustav (čl. 4: „nikad ne iskrivljavaj, ne izostavljaj i ne spinuj") eksplicitno zabranjuje optimizaciju za pažnju na uštrb tačnosti
- Angažovanje je kašnjeni indikator — rano angažovanje će biti nisko ili nula. Ovo nije signal za promjenu kursa
- Kad podaci o angažovanju postoje, koristiti ih kao **kontrolnu tablu** (koje teme rezonuju?) a ne kao **ocjenu** (da li radimo dobro?)

**Obrazloženje (Gudahartov zakon)**: Jednom kad angažovanje postane cilj, sistem će naći načine da ga manipuliše — senzacionalističko uokviravanje, partijanska oštra reagovanja, odabir tema vođen gnjevom. Ovo su upravo ponašanja koja Ustav zabranjuje. Kredibilitet projekta zavisi od toga da *ne* optimizuje za pažnju.

**Posljedice**: Projekat može rasti sporo. Rano angažovanje će biti zanemarljivo. Ovo je prihvatljivo — cilj je pouzdana institucija, ne virusni nalog. Urednički direktor prati potencijal angažovanja kao jednu od nekoliko dimenzija kvaliteta, ali ne nadjačava činjeničnu tačnost ili ustavnu usklađenost.

---

## ADR-023: AGPL-3.0 licenciranje

**Datum**: 2026-02-14
**Status**: Prihvaćeno

**Kontekst**: Kod projekta, promptovi i metodologija su javni (Ustav čl. 22). Licenca mora dozvoliti svakome da ponovo koristi, modifikuje i uči iz rada — ali sprječava komercijalnu eksploataciju ili zatvorene forkove. Alat za vladinu transparentnost ne treba da postane nečiji vlastnički proizvod.

**Odluka**: Licencirati pod **AGPL-3.0** (GNU Affero General Public License v3.0):
- **Dozvoljava**: kopiranje, modifikaciju, redistribuciju, pokretanje softvera u bilo koju svrhu
- **Zahtijeva**: svaka modifikovana verzija — uključujući onu deployovanu kao mrežni servis — mora objaviti svoj kompletan izvorni kod pod AGPL-3.0
- **Efektivno sprječava zatvorenu upotrebu**: obaveza copyleft-a čini vlasničke forkove pravno nemogućim
- **Efektivno odvraća od komercijalne eksploatacije**: većina kompanija neće usvojiti AGPL kod jer ne mogu zadržati modifikacije kao vlasničke. Ovo je praktična barijera, ne pravna zabrana

**Zašto ne eksplicitna nekomercijalna klauzula**:
- Licence sa nekomercijalnim ograničenjima (CC BY-NC-SA, Polyform Noncommercial) OSI ne priznaje kao „otvoreni kod". Ovo ograničava usvajanje od strane zajednice i stvara dvosmislenost (šta se računa kao „komercijalno"?)
- AGPL postiže isti praktični ishod — odvraćanje od komercijalnog preuzimanja — dok ostaje priznata licenca slobodnog softvera
- Ako druga vlada, NVO ili projekat građanske tehnologije želi ovo prilagoditi za svoju zemlju, AGPL im to dozvoljava. Nekomercijalna klauzula bi mogla blokirati legitimnu građansku ponovnu upotrebu od strane organizacija koje tehnički rade komercijalno

**Razmatrane alternative**:
- MIT/Apache — odbijeno: dozvoljava zatvorene forkove i komercijalnu eksploataciju bez obaveza
- GPL-3.0 — odbijeno: copyleft se primjenjuje na distribuciju, ali ima „SaaS rupu" — deployovanje kao veb servis ne pokreće obavezu otkrivanja izvornog koda. AGPL zatvara ovaj propust
- CC BY-NC-SA 4.0 — odbijeno: nije dizajniran za softver (nema odobrenje patenta, nema semantiku povezivanja), FSF i OSI ga ne preporučuju za kod
- Polyform Noncommercial 1.0.0 — odbijeno: eksplicitno nekomercijalan, ali ne zahtijeva da izvedena djela ostanu otvoreni kod

**Posljedice**: Svako može forkovati, prilagoditi i deployovati ovaj projekat — za Crnu Goru, za drugu državu, za bilo koju građansku svrhu — dokle god ga drži otvorenim. Kompanije ga takođe mogu koristiti, ali moraju otvoriti izvorni kod svojih modifikacija. Reputacija AGPL-a kao „licence koju kompanije izbjegavaju" je prednost, ne mana, za ovaj projekat.
