import asyncio
import logging
from websockets import connect
from websockets.exceptions import ConnectionClosedOK, WebSocketException

from ChargePoint import ChargePoint  # Assuming all classes and functions are correctly defined and imported here
from ChargePoint.misc import load_json_config  # Ensure this function is defined to handle config loading

# Setup basic logging
logging.basicConfig(level=logging.INFO)

async def main():
    # Load configuration settings
    charger_config = load_json_config("charger_config.json")
    server_url = charger_config['server_url']
    charger_id = charger_config['charger_id']
    reconnection_delay = charger_config.get('reconnection_delay', 10)  # Default to 10 seconds if not specified

    while True:
        try:
            # Establish WebSocket connection with the central system
            async with connect(f"{server_url}/{charger_id}", subprotocols=["ocpp1.6j"]) as ws:
                # Create an instance of ChargePoint
                cp_instance = ChargePoint(charger_id, ws)

                # Start the ChargePoint operations
                tasks = [
                    cp_instance.start(),
                    cp_instance.boot_sequence(),
                    cp_instance.meter_values_loop(),
                    cp_instance.send_status_notifications_loop()
                    # Add other necessary asynchronous tasks
                ]
                await asyncio.gather(*tasks)

        except ConnectionClosedOK:
            logging.info("WebSocket connection was closed normally, attempting to reconnect...")
            await asyncio.sleep(reconnection_delay)
        except WebSocketException as e:
            logging.error(f"WebSocket error occurred: {e}. Retrying...")
            await asyncio.sleep(reconnection_delay)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await asyncio.sleep(reconnection_delay)
        except KeyboardInterrupt:
            logging.info("Application shutdown requested by user.")
            break

if __name__ == "__main__":
    asyncio.run(main())
