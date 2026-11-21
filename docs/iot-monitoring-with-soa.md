# IoT Monitoring with SOA

> Markdown conversion of the 34-slide PDF presentation. Slide order and original wording are retained as closely as possible. Text has been reorganized into headings and lists; diagrams and screenshots are described in text. Obvious source typos and placeholder text are retained where they appear in the original.

---

## Slide 1 — IoT Monitoring with SOA

**IOT MONITORING WITH SOA**

---

## Slide 2 — Timestamp / Agenda

- Setup check — 5 min
- Introduction — 15 min
- Protocols — 20 min
- Data Fusion — 20 min
- Examples + Exercises — 60 min

---

## Slide 3 — Stile slides

**Stile slides**

---

## Slide 4 — What is SO-IoT?

Service-Oriented IoT (SO-IoT) is an approach to building IoT systems in which sensing, actuation, data processing, monitoring and control are exposed as independent services with defined interfaces.

---

## Slide 5 — Components

- **Things and devices:** Physical or virtual entities that have properties, capabilities and state.
- **Communication and messaging:** Protocols such as MQTT and HTTP allow services to exchange information.
- **Services:** Software components that provide capabilities through defined interfaces.
- **Composition and orchestration:** Multiple services cooperate to achieve a larger goal.

---

## Slide 6 — Layers of SO-IoT

- **Perception / Edge Layer:** Sensors and actuators collect physical data, performing initial pre-processing, analog-to-digital conversion, and local aggregation.
- **Gateway / Fog Layer:** Acts as an interface bridge, often executing lightweight microservices or IoT-as-a-Service (iTaaS) nodes on smart devices or local gateways to stream real-time data efficiently.
- **Cloud / Back-End Layer:** Houses heavy analytics, machine learning for predictive maintenance, digital twin simulations, and centralized dashboard management.

---

## Slide 7 — Design principles

- **Loose coupling:** Services depend on interfaces and message contracts, rather than one another's internal code.
- **Interoperability:** Different implementations can communicate using agreed protocols, formats and semantics.
- **Reusability:** The same weather service or monitoring component can support multiple fields.
- **Independent evolution:** One service can be updated or replaced without redesigning the entire system, provided its interface remains compatible.

---

## Slide 8 — Real world examples

- **Paper on the topic:** *IoT-Based Sensor Monitoring and Automated Irrigation Control for Sustainable Smallholder Vegetable Production: A Case Study*.
- **ThingsBoard:** Device management and data visualization.

**Visual on the slide:** A monitoring dashboard screenshot showing voltage, energy consumption, energy meters, amperage and alarms.

---

## Slide 9 — Architecture

The slide contains an architecture diagram with Docker containers and a central node.

### Diagram elements

- Two groups of device-side **Docker containers** are shown.
- The upper device container includes:
  - Sprinkler actuator
  - Temperature sensor
  - Humidity sensor
  - An ellipsis indicating additional devices
- The lower device container includes:
  - Humidity sensor
  - Temperature sensor
  - Sprinkler actuator
  - An ellipsis indicating additional devices
- A **Central node** runs in its own Docker container.
- A separate Docker container hosts **Dash**.

### Communication shown

- Device sensor data is collected by the central node using **HTTP pull**.
- The central node sends data to **Dash** for visualization.
- The central node communicates with the sprinkler actuators using **MQTT push**.

---

## Slide 10 — Protocols

*3 min*

Four IoT layers: **device, connectivity, gateway, application**.

Connectivity (Zigbee, BLE, Wi-Fi) carries bits. Application protocols (HTTP, MQTT) carry messages.

---

## Slide 11 — Push vs Pull

*4 min*

- **Pull:** The consumer asks.
- **Push:** The source sends when something happens.
- HTTP simulates push (SSE, WebSocket, webhooks).
- MQTT is natively push.
- Real systems are often hybrid.

---

## Slide 12 — HTTP

*4 min*

Request/response over TCP. The client always initiates.

Stateless. Methods say what to do, status codes say what happened.

**Pros:** Universal, easy to debug, firewall-friendly.

**Cons:** Verbose, no native push, heavy for battery devices.

---

## Slide 13 — MQTT

*4 min*

- Lightweight pub/sub: clients talk to a broker, which routes by topic.
- Hierarchical topics with wildcards (`+`, `#`).
- QoS 0/1/2 trades reliability for cost.
- Retained messages give the last state.
- Last Will announces a vanished device.

---

## Slide 14 — What is Data Fusion?

*3 min*

**Hall & Llinas**

> “Data fusion techniques combine data from multiple sensors and related information from associated databases to achieve improved accuracy and more specific inferences than could be achieved by the use of a single sensor alone.”

**Visual on the slide:** Temperature, air humidity and soil moisture (irrigation) are shown as three inputs feeding a Data Fusion component.

---

## Slide 15 — What is Data Fusion? Why Data Fusion?

*2 min*

- To obtain a lower detection error probability and a higher reliability by using data from multiple distributed sources.
- Provide specific benefits for some application contexts.

---

## Slide 16 — Challenges

*3 min*

### Data imperfection

Sensor data is always affected by some level of imprecision and uncertainty (noise, vagueness, ambiguity, incompleteness, limited granularity).

### Data correlation

Dependent data can causes over- or under-confidence on the results if it is not accounted for.

### Data inconsistency

Outliers, spurious data, out-of-sequence arrival and conflicting data.

### Data disparateness

Data comes from sources of different nature with different formats, units and types of uncertainty, so data must first be converted into a common representation.

---

## Slide 17 — Classification of Data Fusion Techniques: By relationship between sources

*3 min*

- **Complementary:** Sources cover different parts of the scene, giving more complete information.
- **Redundant:** Several sources measure the same quantity; data is fused to increase confidence and expose outlier.
- **Cooperative:** Information is combined into new, more complex information.

---

## Slide 18 — Classification of Data Fusion Techniques: By type of architecture

*4 min*

- **Centralized:** All sources send their raw data to a single processor that performs the whole fusion.
- **Decentralized:** There is no central node; each node fuses its own data with the information received from its peers.
- **Distributed:** Each node processes independently an estimate (local view), then the information is sent to the fusion node (global view).
- **Hierarchical:** A combination of the previous types, with fusion performed at different levels.

---

## Slide 19 — Data Fusion for Irrigation

**Data Fusion for Irrigation**

---

## Slide 20 — Examples and Exercises

### Examples

1. **Pull con HTTP:** Interrogare con GET dei sensori di temperatura, gestisce gli errori quando un container viene fermato e fa notare quante richieste risultano inutili.
2. **Push con MQTT:** Sottoscriversi con wildcard ai topic dei sensori, completare una callback `on_message`.
3. Implement the decision to irrigate function (like complete TODOs left in the code together).

### Exercises

1. Make them fine tune the decision function we implemented so that the level of water on the soil remains higher but not too much (between some values in a time range then the test is passed).

---

## Slide 21 — Tecnologies

- **Distribution** → Docker / Docker Compose
- **Protocols** → MQTT / HTTP
- **Architecture** → choose between 2 and 3 from introduction
- **Language** → Python
- **Dashboard** → Dash
- **Algorithms** → VPD (for irrigation), kalman

---

## Slide 22 — Salford AgriTech industrie

**Salford AgriTech industrie**

> “Coltivare un avvenire sostenibile attraverso la tecnologia”

**Visual on the slide:** Salford AgriTech Industries logo and agricultural-field imagery.

---

## Slide 23 — Salford AgriTech industrie: Mission, Vision and Values

**Missione:**

Innovare l'agricoltura mediante la tecnologia per un futuro sostenibile.

**Visione:**

Fornire agli agricoltori soluzioni innovative per nutrire la crescente popolazione globale.

**Valori essenziali:**

Innovazione – Sostenibilità – Trasparenza – Collaborazione

---

## Slide 24 — Sfide dell'agricoltura mondiale

- Aumento della popolazione globale: da 7,7 miliardi (2019) a 8,1 miliardi (2024), prevista a 9,7 miliardi nel 2050 (dati delle Nazioni Unite).
- Entro il 2050, sarà indispensabile incrementare del 70% la produzione alimentare (FAO).
- Impatto del cambiamento climatico: precipitazioni inaspettate, degrado del suolo, scarsità idrica.
- Il 25–30% degli alimenti sprecati a livello globale (FAO, 2023).

---

## Slide 25 — Il ruolo dell'AgriTech

- L'agricoltura intelligente incrementa la produttività dei raccolti del 15–25% (Banca Mondiale, 2022).
- L'agricoltura di precisione consente di ridurre il consumo di acqua fino al 30%.
- L'adozione di droni, IoT, intelligenza artificiale e robotica in agricoltura ha registrato una crescita significativa dal 2015.
- Si prevede che il mercato globale dell'AgriTech raggiungerà i 20,2 miliardi di euro entro il 2025 (Markets&Markets).

---

## Slide 26 — Crescita del mercato e informazioni statistiche

*(Ultimi dieci anni)*

### Espansione del mercato AgriTech

- 2014: ~5 miliardi di euro
- 2020: ~11,7 miliardi di €
- 2024: ~€16,6 miliardi
- Previsione 2030: ~€36 miliardi+

Altri dati riportati nella slide:

- Il 60% degli agricoltori a livello globale impiega almeno uno strumento digitale (McKinsey, 2023).
- Si stima che i dispositivi IoT in agricoltura supereranno i 100 milioni entro il 2030.

---

## Slide 27 — Tecnologia e innovazione

- **Agricoltura di precisione:** Mappatura tramite droni, sensori del terreno, irrigazione intelligente.
- **Intelligenza artificiale e apprendimento automatico:** Analisi predittiva per l'ottimizzazione della resa agricola e la gestione dei parassiti.
- **Biotecnologie:** Colture resistenti alle malattie e resilienti ai cambiamenti climatici.
- **Robotica:** Raccolta automatizzata e sistemi intelligenti.

---

## Slide 28 — Soluzioni per le imprese

- Strumenti per l'agricoltura di precisione (sensori IoT, droni, sistemi di irrigazione intelligente).
- Analisi dei dati per la previsione delle coltivazioni e la salute del terreno.
- Automazione e robotica nelle serre.
- Digitalizzazione della catena di approvvigionamento (tracciabilità e trasparenza).

---

## Slide 29 — Casi di studio e impatto sociale

- Gli agricoltori che hanno implementato la nostra tecnologia hanno registrato un incremento della resa compreso tra il 25% e il 40%.
- Riduzione del consumo idrico fino al 30% grazie all'irrigazione intelligente.
- Una qualità superiore del raccolto conduce a prezzi di mercato più elevati.
- Collaborazione a lungo termine con cooperative e aziende del settore agroalimentare.

---

## Slide 30 — Presenza internazionale e collaborazioni

- Collaborazioni strategiche con istituti di ricerca e autorità governative.
- Progetti attivi in Europa, Asia, Africa e America Latina.
- Collaborazione con università e startup AgriTech.
- Riconoscimento tramite premi per l'innovazione e la sostenibilità.

---

## Slide 31 — Prospettive future

- Piattaforme scalabili fondate sull'intelligenza artificiale per agricoltori di piccole e grandi dimensioni.
- Espansione della presenza globale attraverso progetti sostenibili.
- Impegno a promuovere la sicurezza alimentare globale.
- Guidare l'agricoltura verso un avvenire più sostenibile ed efficiente.

---

## Slide 32 — Salford AgriTech industrie: Contact

**Salford AgriTech industrie**

- Phone: `+123-456-7890`
- Email: `hello@reallygreatsite.com`
- Website: `www.reallygreatsite.com`
- Address: `123 Anywhere St., Any City, ST 12345`

> These contact details appear to be template/demo details in the source slide; they have been transcribed as shown.

---

## Slide 33 — Funding

**FUNDING**

**300K+**

Companies willing to test with us.

---

## Slide 34 — Additional metrics / placeholder slide

The slide title reads **“jahdkjshkjd”** (as shown in the original).

- **Monthly SaaS fee:** 199€
- **Gross margin:** 80%
- **CAC Payback:** 8 months

---

## Conversion notes

- The original is a slide presentation, not a continuous report; each slide is therefore represented as a separate section.
- The architecture and data-fusion illustrations are summarized textually. The dashboard screenshot and agricultural/brand imagery are noted where they add context.
- The source uses both English and Italian. The original language has been retained rather than translated.
- Wording such as “Stile slides”, “Tecnologies”, “can causes”, “expose outlier”, and “jahdkjshkjd” has not been silently corrected.
