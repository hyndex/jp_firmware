import asyncio
import logging
from datetime import datetime

# Placeholder for actual OCPP or system-specific imports
from ocpp.v16 import call
from ocpp.v16.enums import ChargePointStatus

async def send_status_notification(charge_point, connector_id):
    """
    Sends a status update notification for a specific connector.
    :param charge_point: The charge point instance.
    :param connector_id: The identifier of the connector whose status needs updating.
    """
    try:
        # Get the current status and error code from the charge point's status tracking
        status_info = charge_point.connector_status[connector_id]
        status = status_info['status']
        error_code = status_info['error_code']

        # Construct the payload for the status notification
        request = call.StatusNotificationPayload(
            connector_id=connector_id,
            timestamp=datetime.utcnow().isoformat(),
            status=ChargePointStatus[status],
            error_code=error_code
        )
        
        # Send the request and log the action
        response = await charge_point.call(request)
        logging.info(f"Status notification for connector {connector_id} sent successfully: {response}")
        
        if(status_info['status'] != 'Charging'):
            await charge_point.update_specific_lcd_line(connector_id, f'{status_info["status"]} {status_info["error_code"]}')

        # Update the notification sent flag
        status_info['notification_sent'] = True
        logging.info(f"Connector {connector_id} status updated to {status} with error code {error_code}.")
    except KeyError as e:
        logging.error(f"Error accessing connector status: {e}")
    except Exception as e:
        logging.error(f"Error sending status notification for connector {connector_id}: {e}")
