# Roadmap dell’MVP — KZ EcomOps Control Tower

## 1. Obiettivo della roadmap

Questa roadmap divide lo sviluppo in fasi piccole e verificabili. Si passa alla fase successiva solo dopo aver controllato e approvato il risultato della fase corrente.

L’obiettivo dell’MVP è consegnare un’applicazione locale capace di importare CSV sintetici, normalizzare i dati, applicare le regole di riconciliazione e produrre una lista di anomalie comprensibile ed esportabile.

Il primo modulo richiede soltanto `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv` e `refunds.csv`. I file relativi a righe ordine, prodotti, inventario, pubblicità e traffico appartengono alle versioni successive.

## 2. Regola di lavoro

Per ogni fase verrà seguito questo ciclo:

1. spiegazione dell’obiettivo e dei termini nuovi;
2. conferma dell’obiettivo e del perimetro della fase;
3. modifica di un insieme limitato di file;
4. esecuzione dei controlli previsti;
5. riepilogo dei file creati o modificati;
6. approvazione prima della fase seguente.

Non verranno usati dati reali e non verranno installati strumenti senza averne prima spiegato lo scopo.

## 3. Fasi di sviluppo

### Fase 0 — Definizione del progetto

**Obiettivo:** chiarire problema, perimetro, dati e criteri di successo prima di programmare.

**Attività:**

- approvare `PROJECT_OVERVIEW.md`;
- approvare `REQUIREMENTS.md`;
- approvare `DATA_DICTIONARY.md`;
- approvare `MVP_ROADMAP.md`;
- registrare le decisioni definitive elencate nella sezione 5.

**Risultato previsto:** una base documentale coerente e comprensibile, utilizzabile per spiegare il progetto durante un colloquio.

**Controlli:**

- tutte le dieci anomalie richieste sono definite;
- ogni requisito importante può essere verificato;
- i file e le relazioni necessari sono descritti;
- funzioni MVP e funzioni future sono separate chiaramente;
- nessun codice o dipendenza è stato aggiunto.

**Stato:** fase documentale iniziale.

### Fase 1 — Struttura del repository e ambiente Python

**Obiettivo:** creare una struttura professionale minima e un ambiente di sviluppo riproducibile.

**Attività:**

- inizializzare Git soltanto dopo una nuova approvazione;
- preparare il futuro repository con il nome scelto `kz-ecomops-control-tower`, senza rinominare automaticamente la cartella locale attuale;
- creare cartelle per applicazione, test, dati sintetici e documentazione;
- creare un ambiente virtuale Python, cioè uno spazio isolato per le dipendenze del progetto;
- definire le dipendenze iniziali e le relative versioni;
- aggiungere `.gitignore`, licenza MIT e una prima versione del `README.md` principale in inglese con una breve introduzione in italiano; il README inizierà con `# KZ EcomOps Control Tower` e con il sottotitolo `Multi-channel order reconciliation and e-commerce operations analytics.`

**Risultato previsto:** repository ordinato, senza ancora logica aziendale, che può essere preparato su un altro computer seguendo il README.

**Controlli:**

- nessun file locale o segreto viene incluso in Git;
- l’ambiente si crea con le istruzioni documentate;
- la struttura delle cartelle è semplice e motivata;
- codice, cartelle e funzioni usano nomi in inglese;
- le dipendenze installate sono solo quelle necessarie alla fase successiva.

### Fase 2 — Schemi e validazione dei dati

**Obiettivo:** tradurre il dizionario dati in controlli automatici.

**Attività:**

- definire tipi, colonne obbligatorie e valori ammessi per i cinque CSV dell’MVP;
- implementare la lettura sicura dei CSV;
- controllare duplicati, chiavi mancanti, formati e relazioni;
- produrre un report di validazione comprensibile;
- gestire file vuoti con intestazione valida.

**Risultato previsto:** un componente che accetta file validi e spiega con precisione perché rifiuta quelli non validi.

**Controlli:**

- file valido accettato;
- colonna obbligatoria mancante segnalata;
- data o importo non valido segnalato;
- identificativo duplicato segnalato; duplicati di pagamenti e rimborsi conservati per le relative regole di riconciliazione;
- relazione mancante segnalata senza interrompere il programma in modo incomprensibile;
- test automatici della validazione superati.

### Fase 3 — Generazione dei dati sintetici

**Obiettivo:** creare dati inventati ma realistici per dimostrare il progetto senza rischi di privacy.

**Attività:**

- preparare esempi per Shopify, WooCommerce, Amazon ed eBay;
- limitare il dataset iniziale a ordini, pagamenti, spedizioni, resi e rimborsi in EUR;
- includere ordini corretti;
- includere almeno un caso per ciascuna regola `REC-01`–`REC-10`;
- creare file separati per dati validi, dati non validi e scenari di riconciliazione;
- documentare il risultato atteso di ogni scenario.

**Risultato previsto:** dataset ripetibili che rendono le dimostrazioni e i test facili da capire.

**Controlli:**

- nessun dato può essere ricondotto a una persona o azienda reale;
- importi e date sono coerenti con lo scenario dichiarato;
- ogni anomalia attesa è riconoscibile in anticipo;
- sono presenti anche casi che non devono generare anomalie;
- i dati superano la validazione quando lo scenario lo richiede.

### Fase 4 — Normalizzazione e database SQLite

**Obiettivo:** convertire i formati simulati delle piattaforme nel modello comune e salvarli localmente.

**Attività:**

- creare una mappatura separata per ciascuna piattaforma;
- normalizzare soltanto i cinque file obbligatori del primo modulo;
- trasformare nomi delle colonne, stati, date e importi;
- generare identificativi comuni deterministici;
- progettare le tabelle SQLite e le loro relazioni;
- impedire duplicati tecnici durante una nuova importazione;
- conservare il riferimento ai record di origine.

**Risultato previsto:** dati uniformi e interrogabili, indipendenti dal formato originale della piattaforma.

**Controlli:**

- lo stesso concetto produce lo stesso stato normalizzato su tutte le piattaforme;
- chiavi e relazioni nel database sono valide;
- una seconda importazione degli stessi dati non moltiplica i record;
- date, importi e valute mantengono il significato originale;
- i CSV di origine non vengono modificati.

### Fase 5 — Motore di riconciliazione

**Obiettivo:** implementare le dieci regole aziendali senza dipendere dall’interfaccia grafica.

**Attività:**

- creare una struttura comune per le anomalie;
- implementare le regole una alla volta;
- centralizzare tolleranze e soglie temporali;
- registrare valori confrontati e data di riferimento;
- assegnare gravità, descrizione e azione consigliata;
- gestire esplicitamente i controlli non eseguibili.

**Risultato previsto:** dato un insieme normalizzato, il motore restituisce un elenco ripetibile e spiegabile di anomalie.

**Controlli:**

- ogni regola ha un caso che genera l’anomalia;
- ogni regola ha un caso simile che non la genera;
- dati mancanti o valute diverse non producono confronti ingannevoli;
- gli ordini cancellati non risultano semplicemente in ritardo;
- i test automatici di tutte le regole vengono superati.

### Fase 6 — Interfaccia Streamlit

**Obiettivo:** rendere il flusso utilizzabile da una persona non tecnica.

**Attività:**

- creare una pagina di caricamento e validazione;
- utilizzare l’inglese per testi, etichette e messaggi dell’interfaccia;
- mostrare un riepilogo dei record importati;
- consentire l’avvio della riconciliazione;
- mostrare tabella, filtri e dettaglio delle anomalie;
- consentire il cambio dello stato di verifica;
- distinguere visivamente le gravità anche con testo e simboli;
- mostrare motivi chiari per controlli o indicatori non disponibili.

**Risultato previsto:** flusso completo dal caricamento dei CSV alla consultazione delle anomalie.

**Controlli:**

- percorso principale completabile senza usare il terminale dopo l’avvio;
- messaggi di errore comprensibili;
- filtri e stati funzionanti;
- nessun significato affidato soltanto al colore;
- l’interfaccia non contiene logica di riconciliazione duplicata.

### Fase 7 — Esportazione e report operativo

**Obiettivo:** permettere all’utente di portare fuori dall’applicazione il risultato del controllo.

**Attività:**

- esportare le anomalie filtrate in CSV;
- definire ordine e nomi delle colonne esportate;
- includere data di esecuzione e configurazione delle soglie;
- aggiungere conteggi sintetici per codice, gravità, piattaforma e stato.

**Risultato previsto:** un report leggibile e condivisibile che conserva il contesto della riconciliazione.

**Controlli:**

- il CSV esportato si apre correttamente in un foglio di calcolo;
- caratteri accentati, date e decimali restano leggibili;
- l’esportazione rispetta i filtri applicati;
- ogni riga mantiene riferimenti sufficienti per la verifica.

### Fase 8 — Qualità, prestazioni e documentazione finale

**Obiettivo:** verificare che l’MVP sia affidabile, riproducibile e presentabile.

**Attività:**

- eseguire tutti i test automatici;
- provare il volume obiettivo fino a 100.000 righe complessive;
- completare README, guida dimostrativa e spiegazione dell’architettura;
- verificare il repository per segreti e dati reali;
- preparare schermate e uno scenario da colloquio;
- confrontare il risultato con i criteri di completamento.

**Risultato previsto:** MVP pronto per una demo e per la pubblicazione su GitHub.

**Controlli:**

- tutti i criteri in `REQUIREMENTS.md` sono soddisfatti o motivatamente esclusi;
- installazione e avvio vengono provati da zero;
- test superati e prestazioni misurate;
- documentazione coerente con il comportamento reale;
- nessun segreto, dato personale o file temporaneo nel repository;
- limiti noti e prossimi passi dichiarati.

## 4. Ordine consigliato delle tecnologie

Le tecnologie verranno introdotte quando diventano utili:

1. **Python** per la logica del programma;
2. **Pandas** per leggere, controllare e trasformare dati tabellari;
3. **pytest** per verificare automaticamente regole e casi limite;
4. **SQLite** per salvare localmente dati normalizzati e anomalie;
5. **Streamlit** per l’interfaccia web locale;
6. **Plotly** solo quando un grafico migliora realmente il riepilogo.

L’ordine potrà cambiare leggermente durante la progettazione tecnica, ma nessuna dipendenza verrà installata senza spiegazione e approvazione.

## 5. Decisioni definitive

1. **Nome breve e visibile:** `KZ EcomOps Control Tower`.
2. **Nome descrittivo completo:** `KZ E-commerce Operations Control Tower`.
3. **Sottotitolo:** `Multi-channel order reconciliation and e-commerce operations analytics.`
4. **Branding:** `KZ` rappresenta le iniziali e il personal branding del creatore, senza un significato esteso.
5. **Futuro repository GitHub:** `kz-ecomops-control-tower`.
6. **Cartella locale:** non deve essere rinominata automaticamente.
7. **Interfaccia:** inglese.
8. **Codice e struttura:** nomi di codice, colonne, cartelle e funzioni in inglese.
9. **Spiegazioni di sviluppo:** italiano semplice.
10. **README principale:** inglese, con una breve introduzione in italiano; le prime due righe saranno il titolo e il sottotitolo definiti sopra.
11. **Valuta dimostrativa:** solo EUR, con tolleranza monetaria iniziale di `0.01 EUR` e senza conversioni.
12. **Soglia di spedizione:** 48 ore di calendario dalla conferma del pagamento, configurabile.
13. **Soglia di rimborso:** 7 giorni di calendario dalla ricezione del reso, configurabile.
14. **Casi parziali:** spedizioni, resi e rimborsi parziali controllati nell’MVP soltanto sul totale dell’ordine; dettaglio per prodotto rinviato.
15. **Identificativo comune:** `platform:source_order_id`.
16. **Licenza futura:** MIT.

## 6. Funzioni rinviate a versioni future

### Versione successiva — KPI Dashboard

- introduzione e utilizzo di `order_items.csv`, `products.csv`, `ad_spend.csv` e `traffic.csv` quando necessari;
- fatturato, ordini e valore medio dell’ordine;
- margine lordo quando `unit_cost` è disponibile;
- tassi di cancellazione, reso e rimborso;
- tempo medio di evasione e spedizioni puntuali;
- prodotti più venduti e vendite per piattaforma;
- ROAS e costo di acquisizione solo con dati pubblicitari adeguati;
- conversion rate solo con dati di traffico coerenti;
- indicazione esplicita dei KPI non calcolabili.

### Versione successiva — Inventory Optimization

- introduzione e utilizzo di `products.csv`, `order_items.csv` e `inventory.csv`;
- stock basso e rischio di esaurimento;
- vendite medie e giorni di copertura;
- punto di riordino e safety stock semplificata;
- quantità suggerita da riordinare;
- prodotti a vendita rapida o lenta;
- possibili situazioni di overstock;
- inventory turnover, sell-through rate e stockout rate.

### Versioni avanzate — Integrazioni e architettura

- Shopify Admin API e webhook;
- WooCommerce REST API;
- PrestaShop Webservice;
- Amazon Selling Partner API;
- eBay Sell API;
- importazioni programmate e sincronizzazione periodica;
- FastAPI, PostgreSQL e Docker quando esiste una reale esigenza di servizio condiviso;
- autenticazione, ruoli e cronologia multiutente;
- frontend avanzato, eventualmente React;
- notifiche e workflow di assegnazione;
- monitoraggio e distribuzione cloud.
- supporto per USD e altre valute, mantenendo separate le valute e senza confrontare direttamente importi espressi in valute differenti.

## 7. Condizione di chiusura dell’MVP

La roadmap MVP termina quando il flusso completo è funzionante, i criteri di completamento sono verificati, il repository non contiene dati reali e una persona esterna può eseguire la demo seguendo il README.

Qualsiasi funzione aggiuntiva verrà valutata solo dopo questa verifica, per evitare che il progetto diventi troppo grande prima di avere una base stabile.
