# Dizionario dei dati

## 1. Scopo del documento

Il dizionario dei dati descrive i file CSV usati dal progetto e il significato delle loro colonne.

Il documento appartiene a **KZ EcomOps Control Tower**, nome breve di **KZ E-commerce Operations Control Tower**.

I file sintetici potranno imitare esportazioni diverse di Shopify, WooCommerce, Amazon ed eBay. Durante l’importazione, le colonne specifiche di ogni piattaforma verranno **normalizzate**, cioè trasformate nel modello comune descritto qui.

Questo documento definisce quindi il formato comune di destinazione. In una fase successiva verrà creato un documento di mappatura per indicare, per ogni piattaforma, quale colonna originale corrisponde a ciascun campo comune.

## 2. Convenzioni generali

### 2.1 Formato dei file

- codifica testo: UTF-8;
- separatore: virgola;
- prima riga: nomi delle colonne;
- separatore decimale: punto, per esempio `125.50`;
- valori mancanti: campo vuoto, non testi come `N/A`, `null` o `-`;
- valori booleani: `true` oppure `false`;
- date e orari: ISO 8601 con fuso orario, per esempio `2026-08-14T10:30:00+02:00`;
- date senza orario: `YYYY-MM-DD`, per esempio `2026-08-14`;
- valute: nell’MVP è ammesso soltanto il codice ISO 4217 `EUR`; eventuali record con un codice diverso devono essere rifiutati oppure indicati chiaramente come non supportati.

### 2.2 Tipi di dato

- **stringa**: testo;
- **intero**: numero senza decimali;
- **decimale**: numero con decimali, adatto agli importi;
- **booleano**: valore vero o falso;
- **data**: giorno di calendario;
- **data/ora**: data, ora e fuso orario.

### 2.3 Identificativi

Gli identificativi devono essere trattati come stringhe, anche quando contengono solo numeri. In questo modo non si perdono zeri iniziali e si possono gestire prefissi o trattini.

Nei file normalizzati:

- `platform` identifica il sistema di origine;
- `order_id` è l’identificativo comune dell’ordine nel progetto;
- `source_order_id` conserva l’identificativo originale assegnato dalla piattaforma;
- la coppia `platform` + `source_order_id` deve identificare un solo ordine;
- i file collegati usano `order_id` per riferirsi a `orders.csv`.

Il valore di `order_id` deve essere costruito in modo deterministico nel formato `platform:source_order_id`, per esempio `shopify:10542`.

## 3. Elenco dei file CSV

| File | Obbligatorio per l’MVP | Contenuto | Una riga rappresenta |
|---|---:|---|---|
| `orders.csv` | Sì | Testata e stato degli ordini | Un ordine |
| `payments.csv` | Sì | Tentativi e conferme di pagamento | Una transazione di pagamento |
| `shipments.csv` | Sì | Spedizioni associate agli ordini | Una spedizione |
| `returns.csv` | Sì | Richieste e ricezioni di reso | Un reso |
| `refunds.csv` | Sì | Rimborsi associati a ordini o resi | Una transazione di rimborso |
| `order_items.csv` | No — versione futura | Prodotti e quantità di ogni ordine | Una riga di un ordine |
| `products.csv` | No — versione futura | Catalogo comune di prodotti e SKU | Un prodotto/SKU |
| `inventory.csv` | No — versione futura | Quantità disponibili per SKU e sede | Situazione di uno SKU in una sede e data |
| `ad_spend.csv` | No — versione futura | Spesa e risultati pubblicitari | Prestazioni giornaliere di una campagna |
| `traffic.csv` | No — versione futura | Sessioni e conversioni del sito | Prestazioni giornaliere di un canale |

I cinque file obbligatori sono sufficienti per tutte le regole da `REC-01` a `REC-10`. Possono contenere zero righe di dati quando l’evento non si è verificato, ma devono mantenere l’intestazione corretta. Questa scelta consente di distinguere “nessun evento” da “file non fornito”.

I file facoltativi restano documentati per mostrare l’evoluzione prevista del modello, ma la loro assenza non deve bloccare importazione, riconciliazione o completamento dell’MVP.

## 4. `orders.csv`

Contiene una riga per ogni ordine normalizzato.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `order_id` | stringa | Sì | ID univoco comune usato dal progetto. |
| `platform` | stringa | Sì | Origine: `shopify`, `woocommerce`, `amazon` o `ebay`. |
| `source_order_id` | stringa | Sì | ID dell’ordine nella piattaforma di origine. |
| `order_number` | stringa | No | Numero leggibile mostrato all’utente. |
| `ordered_at` | data/ora | Sì | Data e ora di creazione dell’ordine. |
| `order_status` | stringa | Sì | Stato comune: `pending`, `confirmed`, `fulfilled`, `completed` o `cancelled`. |
| `payment_status` | stringa | Sì | Riepilogo pagamento: `pending`, `partially_paid`, `paid`, `failed`, `partially_refunded` o `refunded`. |
| `fulfillment_status` | stringa | Sì | Riepilogo evasione: `unfulfilled`, `partially_fulfilled`, `fulfilled`, `returned` o `cancelled`. |
| `currency` | stringa | Sì | Valuta dell’ordine; nell’MVP deve essere `EUR`. |
| `subtotal` | decimale | Sì | Somma delle righe prima di sconti, spedizione e imposte. Deve essere maggiore o uguale a zero. |
| `discount_total` | decimale | Sì | Totale sconti. Deve essere maggiore o uguale a zero. |
| `shipping_total` | decimale | Sì | Costo di spedizione addebitato. Deve essere maggiore o uguale a zero. |
| `tax_total` | decimale | Sì | Totale imposte. Deve essere maggiore o uguale a zero. |
| `order_total` | decimale | Sì | Totale finale dovuto dal cliente. Deve rispettare la formula documentata sotto. |
| `customer_country` | stringa | No | Codice paese ISO 3166-1 alpha-2, per esempio `US` o `IT`. Non contiene nome o indirizzo del cliente. |
| `cancelled_at` | data/ora | No | Data di cancellazione; obbligatoria se disponibile per un ordine cancellato. |
| `cancellation_reason` | stringa | No | Motivo normalizzato o breve descrizione della cancellazione. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto nella sorgente. |

Formula di controllo iniziale:

`order_total = subtotal - discount_total + shipping_total + tax_total`

È ammessa una differenza massima di `0.01 EUR` dovuta agli arrotondamenti. Eventuali mance, dazi o commissioni richiederanno colonne aggiuntive prima di essere supportati.

## 5. `order_items.csv`

File facoltativo rinviato alle versioni successive. Contiene le righe che compongono un ordine e non è necessario per la riconciliazione iniziale.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `order_item_id` | stringa | Sì | ID univoco della riga ordine. |
| `order_id` | stringa | Sì | Riferimento a `orders.order_id`. |
| `product_id` | stringa | No | Riferimento a `products.product_id`; può mancare per articoli rimossi dal catalogo. |
| `sku` | stringa | Sì | Codice commerciale della variante venduta. |
| `product_name` | stringa | Sì | Nome del prodotto al momento dell’ordine. |
| `quantity` | intero | Sì | Quantità ordinata; deve essere maggiore di zero. |
| `unit_price` | decimale | Sì | Prezzo unitario prima dello sconto di riga. |
| `line_discount` | decimale | Sì | Sconto totale applicato alla riga. |
| `line_tax` | decimale | Sì | Imposta totale applicata alla riga. |
| `line_total` | decimale | Sì | Totale della riga dopo lo sconto e prima o dopo le imposte secondo la convenzione dichiarata. Nell’MVP includerà le imposte. |
| `currency` | stringa | Sì | Deve coincidere con la valuta dell’ordine. |

Formula iniziale:

`line_total = quantity × unit_price - line_discount + line_tax`

## 6. `products.csv`

File facoltativo rinviato alle versioni successive. Contiene il catalogo normalizzato, non è necessario per la riconciliazione iniziale e non deve includere informazioni personali.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `product_id` | stringa | Sì | ID univoco comune del prodotto o della variante. |
| `sku` | stringa | Sì | Codice SKU; deve essere univoco nell’MVP. |
| `product_name` | stringa | Sì | Nome del prodotto. |
| `category` | stringa | No | Categoria commerciale. |
| `brand` | stringa | No | Marchio del prodotto. |
| `unit_cost` | decimale | No | Costo unitario usato in futuro per il margine lordo. |
| `selling_price` | decimale | No | Prezzo di listino corrente. |
| `currency` | stringa | No | Valuta di costo e prezzo; obbligatoria se uno dei due è presente. |
| `lead_time_days` | intero | No | Giorni medi tra ordine al fornitore e disponibilità. |
| `active` | booleano | Sì | Indica se lo SKU è attivo nel catalogo. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto. |

## 7. `payments.csv`

Contiene una riga per ogni transazione o tentativo di pagamento.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `payment_id` | stringa | Sì | ID previsto come univoco per il pagamento. Un valore ripetuto non viene scartato: viene conservato per il controllo `REC-04`. |
| `platform` | stringa | Sì | Sistema che ha fornito il record. |
| `order_id` | stringa | Sì | Riferimento a `orders.order_id`. |
| `source_order_id` | stringa | Sì | ID ordine presente nel sistema sorgente, utile per verificare la mappatura. |
| `provider_transaction_id` | stringa | No | ID assegnato dal provider di pagamento; fortemente raccomandato e necessario per il controllo più affidabile dei duplicati. |
| `payment_method` | stringa | No | Metodo normalizzato, per esempio `card`, `paypal`, `marketplace` o `bank_transfer`. |
| `payment_status` | stringa | Sì | `pending`, `succeeded`, `failed`, `cancelled` o `reversed`. |
| `amount` | decimale | Sì | Importo della transazione; maggiore di zero. |
| `currency` | stringa | Sì | Valuta del pagamento; nell’MVP deve essere `EUR`. |
| `paid_at` | data/ora | No | Momento della conferma; richiesto quando lo stato è `succeeded`. |
| `created_at` | data/ora | Sì | Momento di creazione del record. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto. |

## 8. `shipments.csv`

Un ordine può avere più spedizioni, per esempio quando gli articoli partono da magazzini diversi.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `shipment_id` | stringa | Sì | ID univoco comune della spedizione. |
| `platform` | stringa | Sì | Sistema che ha fornito il record. |
| `order_id` | stringa | Sì | Riferimento a `orders.order_id`. |
| `source_order_id` | stringa | Sì | ID ordine presente nel sistema sorgente. |
| `shipment_status` | stringa | Sì | `pending`, `ready`, `shipped`, `delivered`, `failed`, `cancelled` o `returned`. |
| `carrier` | stringa | No | Nome del corriere. |
| `shipping_service` | stringa | No | Servizio utilizzato, per esempio standard o express. |
| `tracking_number` | stringa | No | Codice di tracking; richiesto dalle regole quando la spedizione è partita. |
| `shipped_at` | data/ora | No | Data di partenza; richiesta per lo stato `shipped` o `delivered`. |
| `delivered_at` | data/ora | No | Data di consegna; richiesta se lo stato è `delivered`. |
| `warehouse_id` | stringa | No | Sede o magazzino di partenza. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto. |

Nell’MVP le spedizioni parziali vengono valutate soltanto sul totale dell’ordine. Non è richiesto indicare quali righe ordine sono presenti in ciascuna spedizione. Il controllo per singolo prodotto, eventualmente tramite un futuro `shipment_items.csv`, è rinviato.

## 9. `returns.csv`

Contiene una riga per ogni pratica di reso.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `return_id` | stringa | Sì | ID univoco comune del reso. |
| `platform` | stringa | Sì | Sistema che ha fornito il record. |
| `order_id` | stringa | Sì | Riferimento a `orders.order_id`. |
| `source_order_id` | stringa | Sì | ID ordine presente nel sistema sorgente. |
| `return_status` | stringa | Sì | `requested`, `approved`, `in_transit`, `received`, `completed`, `rejected` o `cancelled`. |
| `return_reason` | stringa | No | Motivo normalizzato del reso. |
| `requested_at` | data/ora | Sì | Data della richiesta di reso. |
| `received_at` | data/ora | No | Data di ricezione; richiesta per `received` o `completed`. |
| `expected_refund_amount` | decimale | No | Importo che si prevede di rimborsare dopo la verifica. |
| `currency` | stringa | No | Obbligatoria se è presente `expected_refund_amount`; nell’MVP deve essere `EUR`. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto. |

Nell’MVP i resi parziali vengono valutati soltanto sul totale dell’ordine. Il controllo dettagliato per singolo prodotto, eventualmente tramite un futuro `return_items.csv`, è rinviato.

## 10. `refunds.csv`

Contiene una riga per ogni transazione di rimborso.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `refund_id` | stringa | Sì | ID previsto come univoco per il rimborso. Un valore ripetuto non viene scartato: viene conservato per il controllo `REC-09`. |
| `platform` | stringa | Sì | Sistema che ha fornito il record. |
| `order_id` | stringa | Sì | Riferimento a `orders.order_id`. |
| `source_order_id` | stringa | Sì | ID ordine presente nel sistema sorgente. |
| `return_id` | stringa | No | Riferimento a `returns.return_id`; può mancare per rimborsi senza reso. |
| `payment_id` | stringa | No | Pagamento originale a cui è collegato il rimborso. |
| `provider_refund_id` | stringa | No | ID del provider; fortemente raccomandato per riconoscere duplicati. |
| `refund_status` | stringa | Sì | `pending`, `succeeded`, `failed` o `cancelled`. |
| `amount` | decimale | Sì | Importo rimborsato; maggiore di zero. |
| `currency` | stringa | Sì | Valuta del rimborso; nell’MVP deve essere `EUR`. |
| `reason` | stringa | No | Motivo del rimborso. |
| `refunded_at` | data/ora | No | Data di conferma; richiesta quando lo stato è `succeeded`. |
| `created_at` | data/ora | Sì | Data di creazione del record. |
| `updated_at` | data/ora | Sì | Ultimo aggiornamento conosciuto. |

## 11. `inventory.csv`

File facoltativo rinviato al futuro modulo Inventory Optimization. Non partecipa alle dieci regole iniziali di riconciliazione e la sua assenza non blocca l’MVP.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `inventory_record_id` | stringa | Sì | ID univoco della rilevazione. |
| `sku` | stringa | Sì | Riferimento a `products.sku`. |
| `warehouse_id` | stringa | Sì | Sede, magazzino o posizione logica. |
| `snapshot_at` | data/ora | Sì | Momento a cui si riferiscono le quantità. |
| `quantity_on_hand` | intero | Sì | Quantità fisicamente presente. |
| `quantity_reserved` | intero | Sì | Quantità già assegnata a ordini. |
| `quantity_available` | intero | Sì | Quantità vendibile; inizialmente `on_hand - reserved`. |
| `quantity_incoming` | intero | No | Quantità già ordinata ai fornitori ma non ricevuta. |
| `reorder_point` | intero | No | Soglia di riordino, calcolata in futuro. |
| `source_system` | stringa | Sì | Sistema da cui proviene il dato, per esempio `warehouse_csv` o `as400_simulated`. |

Tutte le quantità devono essere maggiori o uguali a zero. Eventuali stock negativi saranno gestiti come errore o anomalia in una fase successiva.

## 12. `ad_spend.csv` — facoltativo e futuro

Questo file servirà per ROAS e costo di acquisizione. Non è richiesto per l’MVP.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `date` | data | Sì | Giorno della rilevazione. |
| `advertising_platform` | stringa | Sì | Per esempio `meta_ads` o `google_ads`. |
| `campaign_id` | stringa | Sì | ID della campagna. |
| `campaign_name` | stringa | No | Nome leggibile della campagna. |
| `spend` | decimale | Sì | Spesa pubblicitaria. |
| `currency` | stringa | Sì | Valuta della spesa. |
| `clicks` | intero | No | Numero di clic. |
| `attributed_orders` | intero | No | Ordini attribuiti secondo la piattaforma pubblicitaria. |
| `attributed_revenue` | decimale | No | Ricavi attribuiti secondo la piattaforma. |

I dati attribuiti dalle piattaforme pubblicitarie non coincidono necessariamente con gli ordini reali; questa differenza dovrà essere spiegata nel modulo KPI.

## 13. `traffic.csv` — facoltativo e futuro

Questo file servirà per conversion rate e analisi del traffico. Non è richiesto per l’MVP.

| Colonna | Tipo | Obbligatoria | Significato e regole |
|---|---|---:|---|
| `date` | data | Sì | Giorno della rilevazione. |
| `site_or_store` | stringa | Sì | Negozio o sito misurato. |
| `channel` | stringa | Sì | Canale, per esempio `organic`, `paid_search`, `paid_social`, `email` o `direct`. |
| `sessions` | intero | Sì | Numero di sessioni. |
| `users` | intero | No | Numero di utenti secondo lo strumento di analytics. |
| `transactions` | intero | No | Transazioni attribuite allo stesso perimetro di traffico. |
| `revenue` | decimale | No | Ricavi attribuiti. |
| `currency` | stringa | No | Obbligatoria se è presente `revenue`. |

## 14. Relazioni tra i dati

Le relazioni obbligatorie dell’MVP sono:

- un ordine può avere zero, uno o più pagamenti;
- un ordine può avere zero, una o più spedizioni;
- un ordine può avere zero, uno o più resi;
- un ordine può avere zero, uno o più rimborsi;
- un reso può avere zero, uno o più rimborsi;
- un pagamento può essere collegato a zero, uno o più rimborsi.

Le relazioni facoltative delle versioni successive sono:

- un ordine in `orders.csv` può avere una o più righe in `order_items.csv`;
- un prodotto in `products.csv` può comparire in molte righe ordine;
- uno SKU può avere più rilevazioni di inventario, in date o magazzini differenti.

Rappresentazione semplificata:

```text
orders ──< payments
   │
   ├────< shipments
   │
   ├────< returns ──< refunds
   │                  >── payments (collegamento facoltativo)
   └────< refunds

products ──< order_items >── orders   (versioni future)
products ──< inventory
```

Il simbolo `──<` significa “uno a molti”. Per esempio, un ordine può avere molti pagamenti.

## 15. Controlli di integrità

Prima della riconciliazione dovranno essere eseguiti almeno questi controlli:

- nessun identificativo obbligatorio è vuoto;
- gli identificativi dichiarati univoci non sono duplicati, con l’eccezione di `payment_id` e `refund_id`: eventuali ripetizioni devono essere conservate e inviate alle regole `REC-04` e `REC-09`;
- ogni `order_id` nei file collegati viene confrontato con `orders.csv`; un riferimento mancante non viene scartato e deve essere valutato da `REC-10`;
- ogni `return_id` valorizzato nei rimborsi viene confrontato con `returns.csv`; un riferimento mancante deve essere valutato da `REC-10`;
- ogni `payment_id` valorizzato nei rimborsi viene confrontato con `payments.csv`; un riferimento mancante deve essere conservato come problema di relazione;
- se vengono forniti i file facoltativi, ogni SKU delle righe ordine e dell’inventario è presente in `products.csv`, salvo eccezioni documentate;
- date e orari seguono il formato previsto;
- quantità e importi rispettano i limiti indicati;
- la valuta dei record collegati coincide con quella dell’ordine;
- tutti i record sintetici dell’MVP che contengono `currency` usano `EUR`; valori diversi vengono rifiutati oppure segnalati come non supportati;
- le date seguono un ordine logico, per esempio `delivered_at` non precede `shipped_at`;
- gli stati appartengono agli elenchi ammessi.

I controlli relativi a `order_items.csv`, `products.csv`, `inventory.csv`, `ad_spend.csv` e `traffic.csv` si applicano soltanto quando tali file verranno introdotti nelle versioni successive. La loro assenza non è un errore nell’MVP.

I record costruiti appositamente per testare dati mancanti dovranno essere marcati nel dataset di test o mantenuti in file dedicati, così da non essere confusi con errori accidentali di preparazione dei dati.

Gli errori di struttura, come colonne obbligatorie assenti o tipi illeggibili, possono bloccare l’elaborazione. I possibili problemi aziendali, come transazioni duplicate o relazioni mancanti, devono invece rimanere disponibili al motore di riconciliazione.

Il supporto per USD e altre valute è rinviato. Un’eventuale versione multivaluta dovrà mantenere separati gli importi per valuta e non confrontare direttamente valori espressi in valute differenti.

## 16. Dati esclusi dall’MVP

Per proteggere la privacy e mantenere il progetto semplice, il modello iniziale non deve contenere:

- nome e cognome del cliente;
- indirizzo completo;
- e-mail o numero di telefono;
- dati della carta di pagamento;
- password, token o chiavi API;
- note interne aziendali reali;
- identificativi reali di account, clienti o transazioni.
