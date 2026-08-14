# KZ EcomOps Control Tower

*Multi-channel order reconciliation and e-commerce operations analytics.*

## 1. Visione del progetto

**KZ EcomOps Control Tower**, nome breve di **KZ E-commerce Operations Control Tower**, è un software dimostrativo per il controllo operativo di un e-commerce multicanale.

Il sistema raccoglie dati provenienti da piattaforme diverse, li converte in un formato comune e li confronta per evidenziare problemi che, se gestiti manualmente, possono essere difficili da individuare.

Il progetto sarà sviluppato in modo progressivo. La prima versione funzionante, chiamata **MVP** (*Minimum Viable Product*, cioè la versione minima che offre già un risultato utile), utilizzerà esclusivamente dati sintetici e file CSV. Non saranno richiesti account, credenziali o dati aziendali reali.

## 2. Problema aziendale

Un’attività e-commerce può ricevere ordini da Shopify, WooCommerce, Amazon, eBay e altri canali. Pagamenti, spedizioni, resi e rimborsi possono essere registrati in sistemi differenti e con formati non uniformi.

Questa frammentazione crea alcuni rischi:

- un ordine può risultare pagato ma non spedito;
- una spedizione può partire senza un pagamento confermato;
- un pagamento o un rimborso può essere registrato due volte;
- un reso ricevuto può non essere ancora rimborsato;
- i dati presenti in due sistemi possono non coincidere;
- i controlli manuali richiedono tempo e possono introdurre errori;
- il responsabile e-commerce può non avere una visione unica e aggiornata delle operazioni.

Il problema centrale è quindi la mancanza di un controllo unificato, ripetibile e facilmente verificabile del ciclo dell’ordine.

## 3. Obiettivo del software

L’obiettivo è costruire uno strumento che aiuti a trasformare esportazioni eterogenee in informazioni operative chiare.

Il software dovrà:

1. importare file CSV che simulano esportazioni da diversi canali di vendita;
2. verificare che i dati ricevuti siano completi e validi;
3. normalizzare i dati, cioè convertirli in una struttura comune;
4. riconciliare ordini, pagamenti, spedizioni, resi e rimborsi;
5. rilevare automaticamente anomalie operative e finanziarie;
6. presentare ogni anomalia con gravità, spiegazione e azione consigliata;
7. permettere l’esportazione dei risultati;
8. creare una base tecnica estendibile con KPI, inventario e API reali.

## 4. Utenti destinatari

### Utenti principali

- **E-commerce Operations Manager**: controlla il corretto avanzamento degli ordini e assegna le verifiche.
- **Order Fulfillment Specialist**: individua ordini bloccati, spedizioni mancanti e problemi di tracking.
- **Customer Service Specialist**: verifica resi, rimborsi e problemi segnalati dai clienti.
- **Inventory o Logistics Coordinator**: in futuro utilizzerà i dati di vendita e stock per pianificare i riordini.

### Utenti secondari

- **Finance o amministrazione**: controlla differenze tra importi ordinati, pagati e rimborsati.
- **E-commerce Analyst**: analizza KPI e trend quando saranno disponibili i moduli successivi.
- **Recruiter o responsabile tecnico**: può valutare il progetto, le scelte progettuali e la capacità di collegare esigenze aziendali e software.

## 5. Funzioni principali

### Funzioni comprese nell’MVP

- caricamento dei cinque file CSV sintetici obbligatori: `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv` e `refunds.csv`;
- supporto iniziale ai canali Shopify, WooCommerce, Amazon ed eBay;
- controllo della struttura e della qualità dei file importati;
- conversione dei dati in un modello comune;
- memorizzazione locale dei dati normalizzati;
- riconciliazione di ordini, pagamenti, spedizioni, resi e rimborsi;
- rilevamento delle dieci categorie minime di anomalie definite in `REQUIREMENTS.md`;
- visualizzazione di un riepilogo dei dati elaborati e delle anomalie;
- filtri per piattaforma, gravità, tipo di problema e stato della verifica;
- esportazione in CSV della lista delle anomalie;
- gestione dello stato di verifica di ogni anomalia.

### Funzioni previste dopo l’MVP

- importazione e utilizzo dei file facoltativi `order_items.csv`, `products.csv`, `inventory.csv`, `ad_spend.csv` e `traffic.csv`;
- dashboard completa dei KPI commerciali e operativi;
- analisi e ottimizzazione dell’inventario;
- suggerimenti di riapprovvigionamento;
- importazioni programmate;
- integrazione con API ufficiali e webhook;
- database condiviso e accesso multiutente;
- autenticazione e ruoli;
- interfaccia frontend più avanzata.

## 6. Benefici attesi

### Benefici operativi

- riduzione del tempo dedicato a confronti manuali;
- identificazione più rapida degli ordini che richiedono attenzione;
- priorità più chiare grazie ai livelli di gravità;
- tracciabilità delle verifiche già eseguite;
- processo di controllo uniforme tra piattaforme diverse.

### Benefici economici e di servizio

- minore rischio di spedire ordini non pagati;
- minore rischio di rimborsi duplicati o superiori al dovuto;
- riduzione dei ritardi di spedizione e di rimborso;
- migliore qualità del customer service;
- maggiore affidabilità dei dati usati per le decisioni.

### Benefici professionali del progetto

Il repository dimostrerà in modo concreto:

- conoscenza del ciclo operativo di un e-commerce;
- capacità di tradurre un problema aziendale in requisiti software;
- gestione e controllo della qualità dei dati;
- uso di Python, Pandas, SQLite, Streamlit, Plotly e pytest in fasi progressive;
- attenzione a documentazione, test, leggibilità e protezione dei dati;
- capacità di progettare un sistema estendibile senza renderlo inutilmente complesso.

## 7. Perimetro della prima versione

L’MVP sarà concentrato sul modulo **Order Reconciliation**. Una schermata di riepilogo potrà mostrare conteggi utili, ma non sarà ancora la dashboard KPI completa.

L’MVP userà:

- dati interamente inventati;
- cinque file CSV locali obbligatori: ordini, pagamenti, spedizioni, resi e rimborsi;
- esclusivamente EUR come valuta dei dati dimostrativi;
- date e orari in formato standard e con fuso orario dichiarato;
- una soglia di spedizione iniziale di 48 ore di calendario dalla conferma del pagamento;
- una soglia di rimborso iniziale di 7 giorni di calendario dalla ricezione del reso;
- soglie operative configurabili;
- controllo di spedizioni, resi e rimborsi parziali soltanto sul totale dell’ordine;
- identificativi comuni nel formato `platform:source_order_id`;
- un database SQLite locale;
- esecuzione su un singolo computer e da parte di un solo utente alla volta.

## 8. Limiti della prima versione

La prima versione:

- non si collegherà ad account reali;
- non richiederà password, token o chiavi API;
- non sincronizzerà dati in tempo reale;
- non modificherà ordini sulle piattaforme di origine;
- non invierà automaticamente e-mail o notifiche;
- non convertirà importi tra valute diverse;
- non gestirà casi fiscali, doganali o contabili complessi;
- non sostituirà un sistema ERP, un gestionale di magazzino o un software contabile;
- non includerà previsioni avanzate basate su machine learning;
- non includerà inizialmente autenticazione, ruoli o collaborazione multiutente;
- non calcolerà KPI privi dei dati necessari;
- non effettuerà controlli per singolo prodotto su spedizioni, resi o rimborsi parziali;
- non userà i risultati per prendere decisioni automatiche senza verifica umana.

## 9. Convenzioni linguistiche e di pubblicazione

- il nome breve e normalmente visibile del prodotto è **KZ EcomOps Control Tower**;
- il nome descrittivo completo è **KZ E-commerce Operations Control Tower**;
- il sottotitolo inglese è *Multi-channel order reconciliation and e-commerce operations analytics.*
- `KZ` rappresenta le iniziali e il personal branding del creatore; non gli viene attribuito un significato esteso;
- il nome previsto per il futuro repository GitHub è `ecommerce-operations-control-tower`;
- la cartella locale attuale non verrà rinominata automaticamente;
- l’interfaccia finale sarà in inglese;
- codice, funzioni, cartelle e colonne useranno nomi in inglese;
- le spiegazioni durante lo sviluppo saranno fornite in italiano semplice;
- il README principale sarà in inglese, conterrà una breve introduzione in italiano e inizierà con:

  ```text
  # KZ EcomOps Control Tower
  Multi-channel order reconciliation and e-commerce operations analytics.
  ```

- la futura licenza del repository sarà MIT.

## 10. Principi di progetto

- **Chiarezza**: nomi, messaggi e documentazione devono essere comprensibili anche a chi è alle prime esperienze.
- **Tracciabilità**: ogni anomalia deve indicare quali dati hanno generato il controllo.
- **Ripetibilità**: elaborando gli stessi file e le stesse regole si devono ottenere gli stessi risultati.
- **Privacy**: il repository pubblico deve contenere soltanto dati sintetici.
- **Qualità**: le regole principali devono essere coperte da test automatici.
- **Semplicità progressiva**: ogni nuova tecnologia verrà aggiunta solo quando risolve un’esigenza concreta.
- **Estendibilità**: le regole di business devono rimanere separate dall’interfaccia, così potranno essere riutilizzate in futuro.

## 11. Risultato atteso dell’MVP

Al termine dell’MVP, un utente dovrà poter caricare un insieme valido di CSV sintetici, avviare il controllo e ottenere una lista affidabile di anomalie, ciascuna accompagnata da una spiegazione semplice e da un’azione consigliata.

Il progetto dovrà essere eseguibile seguendo la documentazione del repository e dovrà includere esempi che mostrino sia casi corretti sia tutte le anomalie previste.
