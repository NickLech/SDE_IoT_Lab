"""Central node entry point: starts the HTTP polling, the MQTT client, the control loop and the HTTP API."""
import logging
import os
import signal
import threading

from components import api, comms
from components.config import PORT, ZONES
from components.control import control_loop

log = logging.getLogger("central")


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    comms.start_polling()
    threading.Thread(target=control_loop, daemon=True, name="control").start()
    comms.start_mqtt()

    server = api.make_server()
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown).start())
    log.info("central started: zones %s, port %d", ZONES, PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    comms.stop_mqtt()


if __name__ == "__main__":
    main()
