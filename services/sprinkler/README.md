# services/sprinkler

Attuatore: 3 valvole (una per zona). Sottoscrive `field/<zone>/sprinkler/cmd` (QoS 1), pubblica lo stato **retained** su `field/<zone>/sprinkler/state` e imposta un Last Will (`offline`). Spegnimento automatico dopo `duration_s`.
