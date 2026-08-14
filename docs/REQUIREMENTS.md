# Requisiti del progetto

## 1. Scopo del documento

Questo documento definisce cosa dovrà fare la prima versione di **KZ E-commerce Operations Control Tower**, normalmente mostrato come **KZ EcomOps Control Tower**, quali caratteristiche qualitative dovrà rispettare e come verrà stabilito se l’MVP è completo.

I requisiti sono identificati da un codice. Per esempio, `RF-01` indica un requisito funzionale e `RNF-01` un requisito non funzionale. I codici rendono più semplice collegare requisiti, attività e test.

## 2. Ambito dell’MVP

L’MVP comprende il modulo **Order Reconciliation**: importazione, validazione, normalizzazione e confronto di ordini, pagamenti, spedizioni, resi e rimborsi.

Il calcolo completo dei KPI e l’ottimizzazione dell’inventario sono moduli successivi. Nell’MVP sarà ammesso solo un riepilogo operativo di base, per esempio numero di record importati e anomalie per gravità.

I soli file obbligatori dell’MVP sono `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv` e `refunds.csv`. Essi devono essere sufficienti per applicare tutte le regole da `REC-01` a `REC-10`.

`order_items.csv`, `products.csv`, `inventory.csv`, `ad_spend.csv` e `traffic.csv` sono facoltativi, appartengono alle versioni successive e non possono essere richiesti per completare o usare il primo modulo.

## 3. Requisiti funzionali

Un requisito funzionale descrive un’azione che il software deve essere in grado di eseguire.

### 3.1 Importazione e validazione

- **RF-01 — Importazione CSV:** il sistema deve importare i cinque file CSV sintetici obbligatori `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv` e `refunds.csv`.
- **RF-02 — Piattaforme supportate:** ogni record deve indicare la piattaforma di origine; i valori iniziali supportati sono `shopify`, `woocommerce`, `amazon` ed `ebay`.
- **RF-03 — Controllo delle colonne:** il sistema deve verificare la presenza delle colonne obbligatorie definite in `DATA_DICTIONARY.md`.
- **RF-04 — Controllo dei tipi:** il sistema deve segnalare valori che non rispettano il tipo previsto, come date non valide o importi non numerici.
- **RF-05 — Controllo dei valori ammessi:** il sistema deve verificare stati, piattaforme e valute rispetto agli elenchi previsti. Nei dati dimostrativi dell’MVP l’unica valuta ammessa è `EUR`; un record con valuta diversa deve essere rifiutato oppure indicato chiaramente come non supportato.
- **RF-06 — Report di importazione:** al termine del caricamento, il sistema deve mostrare file elaborati, record accettati, record scartati e motivi degli errori.
- **RF-07 — Blocco sicuro:** un errore strutturale, come una colonna obbligatoria assente o un importo non leggibile, non deve produrre risultati parziali presentati come completi. Duplicati di pagamento o rimborso e relazioni mancanti tra i cinque file non sono errori strutturali da scartare: devono essere conservati per le regole `REC-04`, `REC-09` e `REC-10`. Il sistema deve indicare chiaramente se la riconciliazione non è stata eseguita.

### 3.2 Normalizzazione e memorizzazione

- **RF-08 — Modello comune:** i dati provenienti da piattaforme diverse devono essere convertiti nelle strutture comuni definite nel dizionario dati.
- **RF-09 — Identificativo univoco:** ogni ordine normalizzato deve conservare la piattaforma e l’identificativo originale. Il suo `order_id` deve seguire il formato `platform:source_order_id`; la coppia `platform` + identificativo di origine deve essere univoca.
- **RF-10 — Date uniformi:** date e orari devono essere convertiti in formato ISO 8601 e mantenere l’informazione sul fuso orario.
- **RF-11 — Importi uniformi:** gli importi monetari devono usare due decimali e rappresentare valori in euro. Tutti i dati dimostrativi dell’MVP devono usare il codice ISO 4217 `EUR` nel campo `currency`.
- **RF-12 — Memorizzazione locale:** i dati normalizzati e le anomalie devono poter essere salvati in un database SQLite locale.
- **RF-13 — Riesecuzione controllata:** ricaricando lo stesso insieme di dati, il sistema non deve creare duplicati tecnici non segnalati.

### 3.3 Riconciliazione

- **RF-14 — Avvio del controllo:** l’utente deve poter avviare la riconciliazione dopo una validazione completata con successo.
- **RF-15 — Regole minime:** il sistema deve applicare tutte le regole da `REC-01` a `REC-10` definite nella sezione 5.
- **RF-16 — Tolleranze configurabili:** le soglie temporali e la tolleranza sugli importi devono essere configurabili senza modificare le regole di business.
- **RF-17 — Assenza di falsi risultati da valuta:** l’MVP non deve effettuare conversioni. Un record diverso da `EUR` deve essere rifiutato oppure segnalato chiaramente come non supportato. Un eventuale supporto multivaluta futuro dovrà mantenere separate le valute e non confrontare direttamente importi espressi in valute differenti.
- **RF-18 — Risultato ripetibile:** gli stessi dati, la stessa configurazione e la stessa data di riferimento devono produrre le stesse anomalie.

### 3.4 Gestione delle anomalie

- **RF-19 — Contenuto minimo:** ogni anomalia deve contenere:
  - identificativo univoco dell’anomalia;
  - codice dell’anomalia;
  - identificativo dell’ordine, quando disponibile;
  - piattaforma;
  - tipo di problema;
  - descrizione semplice;
  - livello di gravità;
  - data e ora di rilevamento;
  - azione consigliata;
  - stato della verifica;
  - riferimenti ai record che hanno generato il controllo.
- **RF-20 — Gravità:** i livelli ammessi devono essere `critical`, `high`, `medium` e `low`.
- **RF-21 — Stato della verifica:** gli stati iniziali ammessi devono essere `open`, `in_review`, `resolved` e `dismissed`.
- **RF-22 — Aggiornamento stato:** l’utente deve poter cambiare lo stato di verifica senza modificare i dati originali importati.
- **RF-23 — Filtri:** l’utente deve poter filtrare le anomalie almeno per piattaforma, codice, gravità e stato.
- **RF-24 — Dettaglio:** selezionando un’anomalia, l’utente deve poter vedere i valori confrontati e la regola applicata.
- **RF-25 — Esportazione:** l’elenco filtrato delle anomalie deve poter essere esportato in CSV.

### 3.5 Riepilogo operativo

- **RF-26 — Indicatori di base:** il sistema deve mostrare almeno numero di ordini importati, importi totali degli ordini, pagamenti validi, spedizioni, resi, rimborsi e anomalie.
- **RF-27 — Distribuzione anomalie:** il sistema deve mostrare il numero di anomalie per codice, gravità, piattaforma e stato.
- **RF-28 — Dati mancanti:** se un indicatore non può essere calcolato, il sistema deve mostrare il motivo invece di usare zero o un valore stimato.

## 4. Requisiti non funzionali

Un requisito non funzionale descrive come il software deve comportarsi, per esempio in termini di sicurezza, chiarezza e affidabilità.

- **RNF-01 — Comprensibilità:** l’interfaccia finale e i relativi messaggi devono essere in inglese e usare un linguaggio semplice e coerente. Le spiegazioni rivolte al proprietario del progetto durante lo sviluppo devono essere in italiano semplice.
- **RNF-02 — Leggibilità del codice:** nomi e struttura del codice dovranno riflettere i concetti aziendali; le funzioni complesse dovranno essere spiegate.
- **RNF-03 — Separazione delle responsabilità:** importazione, validazione, normalizzazione, riconciliazione, memorizzazione e interfaccia dovranno essere componenti distinti.
- **RNF-04 — Testabilità:** ogni regola di riconciliazione dovrà poter essere testata senza avviare l’interfaccia grafica.
- **RNF-05 — Copertura minima:** tutte le regole da `REC-01` a `REC-10` dovranno avere almeno un test positivo, un test senza anomalia e un test con dati mancanti o non validi quando applicabile.
- **RNF-06 — Prestazioni iniziali:** su un computer personale, un insieme dimostrativo fino a 100.000 righe complessive dovrà essere validato e riconciliato in un tempo obiettivo inferiore a 30 secondi. Il valore dovrà essere misurato, non dato per certo.
- **RNF-07 — Integrità dei dati:** i CSV originali non dovranno essere modificati durante l’elaborazione.
- **RNF-08 — Privacy:** esempi, test e documentazione non dovranno contenere dati personali o aziendali reali.
- **RNF-09 — Sicurezza dei segreti:** password, token e chiavi API non dovranno essere richiesti né salvati nell’MVP.
- **RNF-10 — Portabilità:** il progetto dovrà poter essere avviato almeno su Windows, macOS e Linux seguendo istruzioni documentate.
- **RNF-11 — Riproducibilità:** dipendenze e procedura di avvio dovranno essere dichiarate in modo esplicito quando inizierà la programmazione.
- **RNF-12 — Tracciabilità:** ogni anomalia dovrà permettere di risalire alla regola e ai record di origine.
- **RNF-13 — Gestione degli errori:** gli errori dovranno indicare che cosa è successo, in quale file e come correggere il problema.
- **RNF-14 — Accessibilità di base:** testi e colori dell’interfaccia non dovranno affidare il significato esclusivamente al colore.
- **RNF-15 — Manutenibilità:** soglie, stati ammessi e codici delle anomalie dovranno essere centralizzati e documentati.
- **RNF-16 — Controllo versione:** quando il repository Git verrà inizializzato, commit e modifiche dovranno essere piccoli, descrittivi e collegati alle fasi della roadmap.
- **RNF-17 — Convenzioni del progetto:** nomi di codice, funzioni, colonne e cartelle devono essere in inglese.
- **RNF-18 — README:** il README principale dovrà essere in inglese, includere una breve introduzione in italiano e iniziare con il titolo `# KZ EcomOps Control Tower`, seguito dal sottotitolo `Multi-channel order reconciliation and e-commerce operations analytics.`
- **RNF-19 — Licenza:** quando il repository verrà preparato per la pubblicazione, dovrà utilizzare la licenza MIT.

## 5. Regole di riconciliazione

### 5.1 Impostazioni iniziali

Per rendere le regole verificabili, l’MVP userà queste impostazioni iniziali:

- tolleranza per il confronto degli importi: **0.01 EUR**;
- limite per spedire un ordine pagato: **48 ore di calendario** dalla conferma del pagamento;
- limite per rimborsare un reso ricevuto: **7 giorni di calendario** dalla ricezione;
- data di riferimento: data e ora scelte per l’esecuzione del controllo e registrate nel risultato;
- ordini in contrassegno o con pagamento alla consegna: **fuori dal perimetro iniziale**;
- conversione valutaria: **non prevista**;
- valuta dei dati dimostrativi: **solo EUR**;
- spedizioni, resi e rimborsi parziali: **valutati soltanto sul totale dell’ordine**, senza controllo per singolo prodotto.

Le soglie saranno configurabili. La loro modifica non dovrà richiedere la riscrittura delle regole.

### 5.2 Stati considerati

- Un pagamento è confermato se `payment_status` è `succeeded`.
- Una spedizione è partita se `shipment_status` è `shipped` o `delivered`.
- Un reso è ricevuto se `return_status` è `received` o `completed`.
- Un rimborso è valido nel confronto se `refund_status` è `succeeded`.
- I pagamenti e i rimborsi con stato `failed` o `cancelled` non contribuiscono agli importi confermati.

### 5.3 Catalogo delle regole

#### REC-01 — Importo pagato diverso dal totale dell’ordine

- **Codice anomalia:** `PAYMENT_AMOUNT_MISMATCH`
- **Condizione:** la somma dei pagamenti confermati, al netto di eventuali storni di pagamento rappresentati nei dati, differisce da `order_total` per più della tolleranza.
- **Applicazione:** ordini che risultano pagati o parzialmente pagati e per i quali i dati hanno la stessa valuta.
- **Gravità iniziale:** `high`.
- **Azione consigliata:** confrontare ordine e transazioni nel canale di vendita e nel provider di pagamento.

#### REC-02 — Ordine pagato ma non spedito entro il limite

- **Codice anomalia:** `PAID_NOT_SHIPPED_ON_TIME`
- **Condizione:** il pagamento completo è confermato, l’ordine non è cancellato, non esiste una spedizione partita e sono trascorse più di 48 ore dalla conferma del pagamento.
- **Gravità iniziale:** `medium`; diventa `high` se il ritardo supera una successiva soglia configurabile.
- **Azione consigliata:** verificare disponibilità, blocchi del magazzino e stato del fulfillment.

#### REC-03 — Ordine spedito senza pagamento confermato

- **Codice anomalia:** `SHIPPED_WITHOUT_CONFIRMED_PAYMENT`
- **Condizione:** esiste una spedizione partita, ma la somma dei pagamenti confermati è inferiore al totale dell’ordine oltre la tolleranza.
- **Gravità iniziale:** `critical`.
- **Azione consigliata:** verificare immediatamente pagamento, metodo utilizzato e possibilità di recupero dell’importo.

#### REC-04 — Pagamento duplicato

- **Codice anomalia:** `DUPLICATE_PAYMENT`
- **Condizione:** lo stesso `provider_transaction_id` compare più di una volta per la stessa piattaforma oppure lo stesso `payment_id` è ripetuto. In assenza dell’identificativo del provider, il sistema può segnalare solo record perfettamente identici come possibile duplicato.
- **Gravità iniziale:** `high`.
- **Azione consigliata:** verificare le transazioni e rimborsare un eventuale addebito duplicato solo dopo conferma umana.

#### REC-05 — Spedizione senza tracking

- **Codice anomalia:** `SHIPMENT_WITHOUT_TRACKING`
- **Condizione:** una spedizione ha stato `shipped` o `delivered`, ma `tracking_number` è vuoto.
- **Gravità iniziale:** `medium`.
- **Azione consigliata:** recuperare il codice dal corriere e aggiornare il canale di vendita.

#### REC-06 — Ordine cancellato ma spedito

- **Codice anomalia:** `CANCELLED_ORDER_SHIPPED`
- **Condizione:** `order_status` è `cancelled` e per lo stesso ordine esiste una spedizione con stato `shipped` o `delivered`.
- **Gravità iniziale:** `critical`.
- **Azione consigliata:** verificare la possibilità di bloccare la consegna e controllare pagamento e rimborso.

#### REC-07 — Reso ricevuto ma non rimborsato

- **Codice anomalia:** `RETURN_RECEIVED_NOT_REFUNDED`
- **Condizione:** il reso è stato ricevuto, sono trascorsi più di 7 giorni e non esiste un rimborso confermato per lo stesso ordine, collegato tramite `return_id` quando disponibile. Se è previsto un rimborso parziale, il confronto avviene soltanto sul totale atteso dell’ordine e il valore atteso deve essere disponibile. Senza un valore atteso, la regola può rilevare l’assenza completa del rimborso ma non stabilire se un rimborso parziale sia sufficiente.
- **Gravità iniziale:** `high`.
- **Azione consigliata:** verificare l’esito dell’ispezione del reso e completare o documentare il rimborso.

#### REC-08 — Rimborso superiore al valore pagato

- **Codice anomalia:** `REFUND_EXCEEDS_PAYMENT`
- **Condizione:** la somma dei rimborsi confermati dell’ordine supera la somma dei pagamenti confermati oltre la tolleranza.
- **Gravità iniziale:** `critical`.
- **Azione consigliata:** bloccare ulteriori rimborsi e verificare immediatamente tutte le transazioni dell’ordine.

#### REC-09 — Rimborso duplicato

- **Codice anomalia:** `DUPLICATE_REFUND`
- **Condizione:** lo stesso `provider_refund_id` compare più di una volta per la stessa piattaforma oppure lo stesso `refund_id` è ripetuto. In assenza dell’identificativo del provider, il sistema può segnalare solo record perfettamente identici come possibile duplicato.
- **Gravità iniziale:** `critical`.
- **Azione consigliata:** verificare i movimenti presso il provider di pagamento e impedire ulteriori accrediti.

#### REC-10 — Record presente in un sistema ma assente negli altri

- **Codice anomalia:** `CROSS_SYSTEM_RECORD_MISSING`
- **Condizione:** un pagamento, una spedizione, un reso o un rimborso fa riferimento a un `order_id` che non esiste negli ordini; oppure lo stato dell’ordine dichiara un evento completato ma il relativo record di dettaglio non esiste. Esempi: ordine `paid` senza pagamento confermato, ordine `fulfilled` senza spedizione, rimborso riferito a un reso inesistente quando `return_id` è valorizzato.
- **Gravità iniziale:** `high`; `critical` se il record mancante impedisce di verificare un movimento finanziario.
- **Azione consigliata:** controllare completezza delle esportazioni, mappatura degli identificativi e sincronizzazione tra sistemi.

### 5.4 Prevenzione dei falsi positivi

Un falso positivo è una segnalazione che sembra un problema, ma non lo è. Per limitarli:

- i confronti monetari devono avvenire solo nella stessa valuta;
- l’assenza di un file obbligatorio deve bloccare il controllo collegato, non generare automaticamente anomalie per tutti gli ordini;
- record falliti o cancellati non devono contribuire ai totali confermati;
- gli ordini cancellati non devono essere segnalati come in ritardo di spedizione;
- le regole temporali devono usare una data di riferimento esplicita;
- ogni controllo non eseguibile deve risultare come “non valutato” con una motivazione.

## 6. Criteri di completamento dell’MVP

L’MVP può essere considerato completato solo quando tutti i criteri seguenti sono soddisfatti.

### 6.1 Funzioni

- `orders.csv`, `payments.csv`, `shipments.csv`, `returns.csv` e `refunds.csv` possono essere caricati e validati;
- nessuno dei file facoltativi `order_items.csv`, `products.csv`, `inventory.csv`, `ad_spend.csv` e `traffic.csv` è necessario per completare o usare la riconciliazione;
- i quattro canali iniziali possono essere rappresentati nei dati sintetici;
- i dati validi vengono normalizzati e salvati in SQLite;
- tutte le regole da `REC-01` a `REC-10` sono implementate;
- ogni anomalia contiene tutti i campi previsti da `RF-19`;
- filtri, dettaglio, cambio stato ed esportazione CSV funzionano;
- il sistema distingue tra valore zero e KPI o controllo non calcolabile.

### 6.2 Qualità

- il progetto contiene dati sintetici per almeno un caso corretto e un caso anomalo per ogni regola;
- i test automatici previsti da `RNF-05` vengono superati;
- due esecuzioni con gli stessi dati e la stessa data di riferimento producono gli stessi risultati;
- un file con colonna mancante o tipo errato produce un messaggio comprensibile; una relazione mancante destinata a `REC-10` produce un’anomalia comprensibile senza perdere il record;
- nessun dato reale, segreto o credenziale è presente nel repository;
- la prova con il volume indicato in `RNF-06` è stata eseguita e documentata;
- la documentazione spiega installazione, avvio, dati di esempio, regole e limiti.

### 6.3 Dimostrazione finale

Una persona che non ha sviluppato il progetto deve poter, seguendo la documentazione:

1. preparare l’ambiente;
2. avviare l’applicazione;
3. caricare i file dimostrativi;
4. eseguire la riconciliazione;
5. capire perché è stata generata un’anomalia;
6. filtrare e aggiornare lo stato di una verifica;
7. esportare il risultato.

## 7. Fuori dal perimetro dell’MVP

Non sono criteri di completamento dell’MVP:

- collegamenti alle API ufficiali;
- sincronizzazione automatica o in tempo reale;
- dashboard KPI completa;
- previsioni di domanda e ottimizzazione dell’inventario;
- conversione tra valute;
- supporto per USD o altre valute, previsto soltanto come possibile sviluppo futuro;
- autenticazione, ruoli e multiutenza;
- PostgreSQL, Docker, FastAPI o React;
- invio di notifiche;
- modifiche automatiche sui sistemi sorgente;
- controlli di spedizioni, resi e rimborsi parziali a livello di singolo prodotto;
- uso obbligatorio di `order_items.csv`, `products.csv`, `inventory.csv`, `ad_spend.csv` o `traffic.csv`.
