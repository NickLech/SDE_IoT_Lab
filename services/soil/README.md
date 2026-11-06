# services/soil

Container sensore **umidità del suolo**. Simula 9 sensori (3 ridondanti per zona), pubblica su MQTT (**push**) ogni ~2 s su `field/<zone>/soil/<sensor_id>`.

Comportamento:
- il suolo si asciuga lentamente (tasso diverso per zona);
- sottoscrive `field/<zone>/sprinkler/state`: se `on`, l'umidità sale;
- rumore, spike e guasto iniettabile (`debug/<sensor_id>/fault`).
